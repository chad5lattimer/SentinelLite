"""Baseline creation and validation for SentinelLite.

Per PROJECT_SPEC.md section 9 (Baseline Creation) and section 6.2 (Baseline
data model):
    - A baseline is created by recursively hashing every file in a
      monitored directory (delegated to ``core.filesystem.scan_directory``).
    - The baseline is the trust reference for all future scans (section
      17.2) -- this module has no storage or GUI logic; persistence is
      handled by ``storage.repository`` and the "warn before replacing an
      existing baseline" UX lives in the GUI layer (Run 5), which can use
      ``storage.repository.BaselineRepository.has_baseline`` to decide
      whether to prompt.

This module also defines the baseline validation used when reading a
baseline back from storage, so a corrupted or malformed baseline is
reported clearly instead of crashing the application (PROJECT_SPEC.md
section 19, "Corrupted baseline is handled").
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from config import APP_VERSION
from core.filesystem import ProgressCallback, scan_directory
from core.models import Baseline, FileError, FileRecord

logger = logging.getLogger(__name__)


class BaselineError(Exception):
    """Raised when a baseline cannot be created, read, or is malformed.

    Callers (GUI, CLI) should catch this and present a user-friendly
    message per PROJECT_SPEC.md section 18; the original cause is chained
    (``raise ... from err``) so full detail remains available in the log.
    """


def create_baseline(
    root: Path,
    progress_callback: ProgressCallback | None = None,
    chunk_size: int | None = None,
) -> tuple[Baseline, list[FileError]]:
    """Create a new, unsaved baseline from every file under ``root``.

    Args:
        root: Directory to baseline. Must exist and be a directory.
        progress_callback: Optional progress callback, forwarded to
            ``scan_directory`` (PROJECT_SPEC.md section 13).
        chunk_size: Optional hashing chunk-size override, forwarded to
            ``scan_directory``.

    Returns:
        A tuple ``(baseline, errors)``. ``baseline.baseline_id`` is
        ``None`` -- callers must persist it via
        ``storage.repository.BaselineRepository.save_baseline`` to obtain
        an id. ``errors`` lists any files that could not be read and so
        are absent from the baseline, so the caller can inform the user
        (PROJECT_SPEC.md section 7.3).

    Raises:
        NotADirectoryError: If ``root`` does not exist or is not a
            directory.
    """
    root = Path(root)
    records, errors = scan_directory(root, progress_callback=progress_callback, chunk_size=chunk_size)

    baseline = Baseline(
        baseline_id=None,
        created_at=datetime.now(timezone.utc).isoformat(),
        root_directory=str(root),
        application_version=APP_VERSION,
        files=tuple(records),
    )

    logger.info(
        "Created baseline for %s: %d files, %d unreadable.",
        root,
        len(records),
        len(errors),
    )
    if errors:
        logger.warning("Baseline for %s excludes %d unreadable file(s).", root, len(errors))

    return baseline, errors


def validate_baseline(baseline: Baseline) -> None:
    """Validate that a baseline read back from storage is well-formed.

    Raises:
        BaselineError: If any required field is missing, of the wrong
            type, or a file entry is malformed. This is what allows a
            corrupted baseline (e.g. a database row with missing/garbled
            columns) to be reported as a friendly error rather than
            crashing the application or silently proceeding with bad
            data (PROJECT_SPEC.md section 19).
    """
    if not isinstance(baseline, Baseline):
        raise BaselineError(f"Expected a Baseline, got {type(baseline).__name__}.")

    if not baseline.root_directory:
        raise BaselineError("Baseline is missing its root directory.")

    if not baseline.created_at:
        raise BaselineError("Baseline is missing its creation timestamp.")

    _validate_files(baseline.files)


def _validate_files(files: Iterable[FileRecord]) -> None:
    seen_paths: set[str] = set()
    for entry in files:
        if not isinstance(entry, FileRecord):
            raise BaselineError(f"Baseline contains a malformed file entry: {entry!r}.")
        if not entry.path:
            raise BaselineError("Baseline contains a file entry with an empty path.")
        if entry.path in seen_paths:
            raise BaselineError(f"Baseline contains a duplicate path: {entry.path!r}.")
        seen_paths.add(entry.path)
        if len(entry.sha256) != 64:
            raise BaselineError(f"Baseline entry {entry.path!r} has an invalid SHA-256 hash.")
        if entry.size < 0:
            raise BaselineError(f"Baseline entry {entry.path!r} has a negative size.")
