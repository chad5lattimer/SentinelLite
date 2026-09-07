"""Baseline creation, persistence, and loading for SentinelLite.

Per PROJECT_SPEC.md section 9 (Baseline Creation) and section 28 (Run 3):
    - A baseline captures every readable file under a monitored directory
      (enumerated and hashed by ``core.filesystem``) along with metadata
      describing when and where it was created.
    - Baselines are persisted locally via SQLite (``storage.database`` /
      ``storage.repository``) and can be reloaded later.
    - A missing or corrupted baseline must be handled gracefully rather
      than crashing the application (section 19).

This module contains the baseline data structure plus the orchestration
between the filesystem/hashing engine (``core.filesystem``) and the
storage layer (``storage.repository``). Deciding *when* to create a
baseline, and warning the user that doing so replaces the active
monitoring reference, is a GUI concern (section 9) handled in Run 5 --
this module simply performs the operation once asked.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from config import APP_VERSION
from core.filesystem import ProgressCallback, scan_directory
from core.models import FileError, FileRecord
from storage import repository
from storage.database import DatabaseCorruptedError

logger = logging.getLogger(__name__)

__all__ = [
    "Baseline",
    "BaselineNotFoundError",
    "DatabaseCorruptedError",
    "create_baseline",
    "save_baseline",
    "load_baseline",
]


class BaselineNotFoundError(Exception):
    """Raised when loading a baseline that does not exist.

    Covers both "no baseline has ever been created" (PROJECT_SPEC.md
    section 24: "No baseline exists. Create a baseline before scanning.")
    and "the requested baseline id does not exist".
    """


@dataclass(frozen=True)
class Baseline:
    """A cryptographic baseline of a monitored directory's files.

    Per PROJECT_SPEC.md section 6.2. ``baseline_id`` is ``None`` until the
    baseline has been persisted via ``save_baseline``.
    """

    root_directory: str
    created_at: str
    application_version: str
    files: tuple[FileRecord, ...] = field(default_factory=tuple)
    baseline_id: int | None = None

    @property
    def file_count(self) -> int:
        return len(self.files)


def create_baseline(
    root: Path,
    progress_callback: ProgressCallback | None = None,
    chunk_size: int | None = None,
) -> tuple[Baseline, list[FileError]]:
    """Enumerate and hash every file under ``root`` to build a new baseline.

    This does not persist anything -- call ``save_baseline`` with the
    result to write it to storage. Splitting creation from saving keeps
    this function testable without a database and lets the GUI show a
    confirmation ("Baseline Created" / file count) before committing.

    Returns:
        A tuple ``(baseline, errors)``. ``baseline.baseline_id`` is
        ``None`` (not yet saved). ``errors`` lists any files that could
        not be read (PROJECT_SPEC.md section 7.3) -- they are excluded
        from the baseline but reported so the user can be informed.

    Raises:
        NotADirectoryError: If ``root`` is not an existing directory
            (propagated from ``core.filesystem.scan_directory``).
    """
    records, errors = scan_directory(root, progress_callback=progress_callback, chunk_size=chunk_size)

    baseline = Baseline(
        root_directory=str(root),
        created_at=datetime.now(timezone.utc).isoformat(),
        application_version=APP_VERSION,
        files=tuple(records),
    )

    logger.info(
        "Baseline created in memory for %s: %d files, %d unreadable.",
        root,
        len(records),
        len(errors),
    )
    if errors:
        for error in errors:
            logger.warning("Baseline excludes unreadable file %s: %s", error.path, error.message)

    return baseline, errors


def save_baseline(connection: sqlite3.Connection, baseline: Baseline) -> Baseline:
    """Persist ``baseline`` as a new baseline row, returning it with its id set.

    Every call creates a new baseline; it never overwrites a prior one in
    place, so scan history against earlier baselines is preserved. The
    caller (GUI, Run 5) is responsible for warning the user before calling
    this when an active baseline already exists (PROJECT_SPEC.md section 9).
    """
    baseline_id = repository.insert_baseline(
        connection,
        created_at=baseline.created_at,
        root_directory=baseline.root_directory,
        application_version=baseline.application_version,
        files=baseline.files,
    )
    logger.info(
        "Baseline #%d saved: %d files from %s.",
        baseline_id,
        baseline.file_count,
        baseline.root_directory,
    )
    return Baseline(
        root_directory=baseline.root_directory,
        created_at=baseline.created_at,
        application_version=baseline.application_version,
        files=baseline.files,
        baseline_id=baseline_id,
    )


def load_baseline(connection: sqlite3.Connection, baseline_id: int | None = None) -> Baseline:
    """Load a baseline from storage.

    Args:
        connection: An open database connection (see ``storage.database``).
        baseline_id: The baseline to load. If omitted, the most recently
            created baseline is loaded.

    Raises:
        BaselineNotFoundError: If no baseline exists (``baseline_id`` is
            omitted and no baseline has ever been saved) or the requested
            ``baseline_id`` does not exist. Callers are expected to
            translate this into a user-friendly message such as "No
            baseline exists. Create a baseline before scanning."
            (PROJECT_SPEC.md section 24).
    """
    if baseline_id is None:
        baseline_id = repository.get_latest_baseline_id(connection)
        if baseline_id is None:
            raise BaselineNotFoundError("No baseline exists.")

    metadata = repository.get_baseline_metadata(connection, baseline_id)
    if metadata is None:
        raise BaselineNotFoundError(f"Baseline #{baseline_id} does not exist.")

    files = repository.get_baseline_files(connection, baseline_id)

    logger.info("Baseline #%d loaded: %d files from %s.", baseline_id, len(files), metadata.root_directory)

    return Baseline(
        root_directory=metadata.root_directory,
        created_at=metadata.created_at,
        application_version=metadata.application_version,
        files=tuple(files),
        baseline_id=metadata.baseline_id,
    )
