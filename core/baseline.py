"""Baseline creation and loading for SentinelLite.

Per PROJECT_SPEC.md section 6.2 (Baseline) and section 9 (Baseline
Creation):
    - A baseline captures the full set of ``FileRecord``s for a monitored
      directory at a point in time, plus metadata (id, creation time, root
      directory, application version).
    - Creating a new baseline for a directory replaces the prior one --
      persistence (and thus the replacement) is delegated to
      ``storage.repository.BaselineRepository``.

This module has no SQLite or GUI code: it composes ``core.filesystem``
(enumeration/hashing) with a ``BaselineRepository`` (storage), matching the
layered architecture in PROJECT_SPEC.md section 5.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from config import APP_VERSION
from core.filesystem import ProgressCallback, scan_directory
from core.models import FileError, FileRecord

if TYPE_CHECKING:
    from storage.repository import BaselineRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Baseline:
    """A saved snapshot of a monitored directory (PROJECT_SPEC.md section 6.2).

    Attributes:
        baseline_id: Database id of this baseline, or ``None`` if it has
            been created in memory but not yet saved.
        created_at: ISO-8601 UTC timestamp of when the baseline was created.
        root_directory: Absolute path of the monitored directory, as given
            by the caller (not the individual file paths, which are stored
            relative to it -- see ``core.models.FileRecord``).
        application_version: The SentinelLite version that created this
            baseline, for future compatibility/debugging.
        files: The hashed files captured in this baseline.
    """

    root_directory: str
    files: list[FileRecord] = field(default_factory=list)
    created_at: str = ""
    application_version: str = APP_VERSION
    baseline_id: int | None = None


def create_baseline(
    root_directory: Path,
    repository: "BaselineRepository",
    progress_callback: ProgressCallback | None = None,
) -> tuple[Baseline, list[FileError]]:
    """Enumerate, hash, and save a new baseline for ``root_directory``.

    Implements PROJECT_SPEC.md section 9: enumerate files, hash each file,
    save the baseline. Confirming the directory with the user and warning
    that this replaces the existing baseline (also section 9) are GUI
    concerns (Run 5) -- this function performs the replacement once called.

    Args:
        root_directory: Directory to baseline. Must exist and be a
            directory (``core.filesystem.scan_directory`` raises
            ``NotADirectoryError`` otherwise).
        repository: Where to persist the resulting baseline.
        progress_callback: Optional progress callback, forwarded to
            ``scan_directory`` (PROJECT_SPEC.md section 13).

    Returns:
        A tuple ``(baseline, errors)``: the saved ``Baseline`` (with
        ``baseline_id`` populated) and any per-file errors encountered
        while scanning (PROJECT_SPEC.md section 7.3) -- these do not
        prevent the baseline from being created from the files that *were*
        readable.
    """
    root_directory = Path(root_directory)
    records, errors = scan_directory(root_directory, progress_callback=progress_callback)

    baseline = Baseline(
        root_directory=str(root_directory),
        files=records,
        created_at=datetime.now(timezone.utc).isoformat(),
        application_version=APP_VERSION,
    )

    baseline_id = repository.save(baseline)
    saved_baseline = Baseline(
        root_directory=baseline.root_directory,
        files=baseline.files,
        created_at=baseline.created_at,
        application_version=baseline.application_version,
        baseline_id=baseline_id,
    )

    logger.info(
        "Baseline created for %s: %d files, %d errors",
        saved_baseline.root_directory,
        len(saved_baseline.files),
        len(errors),
    )
    if errors:
        for error in errors:
            logger.warning("Baseline creation could not read %s: %s", error.path, error.message)

    return saved_baseline, errors


def load_baseline(root_directory: Path, repository: "BaselineRepository") -> Baseline:
    """Load the current baseline for ``root_directory``.

    A thin, symmetric counterpart to ``create_baseline`` for callers that
    only need to read the existing baseline (e.g. before a scan in Run 4).
    Propagates ``storage.repository.BaselineNotFoundError`` /
    ``BaselineCorruptedError`` unchanged so callers can distinguish "no
    baseline yet" from "baseline is damaged" (PROJECT_SPEC.md section 19).
    """
    return repository.load_latest_for_directory(str(Path(root_directory)))
