"""Baseline creation and validation for SentinelLite.

Per PROJECT_SPEC.md section 6.2 (Baseline) and section 9 (Baseline
Creation). A Baseline is the cryptographic trust reference used later by
core.scanner (Run 4) to detect NEW/MODIFIED/DELETED/UNCHANGED files.

This module is storage-agnostic: it knows how to build and validate a
Baseline from a directory scan, but has no SQLite or GUI dependency --
persistence lives in storage.repository, which sits above this module in
the layered architecture (PROJECT_SPEC.md section 5).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from config import APP_VERSION
from core.filesystem import ProgressCallback, scan_directory
from core.models import FileError

#: Length of a hex-encoded SHA-256 digest, used by validate_baseline().
_SHA256_HEX_LENGTH = 64


@dataclass(frozen=True)
class BaselineFile:
    """A single file recorded in a baseline, per PROJECT_SPEC.md section 6.2.

    ``relative_path`` uses forward slashes (see core.filesystem) so
    baselines are portable across operating systems.
    """

    relative_path: str
    sha256: str
    size: int
    modified_time: float


@dataclass(frozen=True)
class Baseline:
    """A cryptographic baseline: the trust reference for a monitored directory.

    ``baseline_id`` is ``None`` until the baseline has been persisted via
    ``storage.repository.BaselineRepository.save()``, which assigns the
    database-issued id.
    """

    root_directory: str
    created_at: str
    application_version: str
    files: tuple[BaselineFile, ...]
    baseline_id: int | None = None

    @property
    def file_count(self) -> int:
        return len(self.files)


class BaselineValidationError(Exception):
    """Raised when a Baseline is structurally invalid or corrupted.

    Covers both a freshly built Baseline (programmer error) and one loaded
    from storage that has been damaged (PROJECT_SPEC.md section 19 --
    "Corrupted baseline is handled").
    """


def create_baseline(
    root: Path,
    *,
    chunk_size: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> tuple[Baseline, list[FileError]]:
    """Enumerate and hash every file under ``root`` and build a new Baseline.

    Files that cannot be read are excluded from the baseline -- they cannot
    serve as a trust reference for content that was never hashed -- and are
    returned separately as ``FileError`` entries, per PROJECT_SPEC.md
    section 7.3. The caller (the GUI, Run 5) is responsible for informing
    the user about them; this function does not raise for individual
    unreadable files.

    The returned Baseline has ``baseline_id=None``; it is assigned once
    saved via ``storage.repository.BaselineRepository.save()``.

    Args:
        root: Directory to baseline. Must exist and be a directory.
        chunk_size: Optional override for the hashing chunk size, in bytes.
        progress_callback: Optional callback forwarded to
            ``core.filesystem.scan_directory`` (PROJECT_SPEC.md section 13).

    Raises:
        NotADirectoryError: If ``root`` does not exist or is not a
            directory.
    """
    records, errors = scan_directory(root, progress_callback=progress_callback, chunk_size=chunk_size)

    files = tuple(
        BaselineFile(
            relative_path=record.path,
            sha256=record.sha256,
            size=record.size,
            modified_time=record.modified_time,
        )
        for record in records
    )
    baseline = Baseline(
        root_directory=str(Path(root)),
        created_at=datetime.now(timezone.utc).isoformat(),
        application_version=APP_VERSION,
        files=files,
    )
    return baseline, errors


def validate_baseline(baseline: Baseline) -> None:
    """Validate that ``baseline`` is structurally sound.

    Used after loading a baseline from storage to detect corruption
    (PROJECT_SPEC.md section 19 -- "Corrupted baseline is handled") before
    it is trusted as a comparison reference.

    Raises:
        BaselineValidationError: If a required field is missing/empty, a
            file entry has an invalid value, or the same relative path
            appears more than once.
    """
    if not baseline.root_directory:
        raise BaselineValidationError("Baseline is missing a root directory.")
    if not baseline.created_at:
        raise BaselineValidationError("Baseline is missing a creation timestamp.")
    if not baseline.application_version:
        raise BaselineValidationError("Baseline is missing an application version.")

    seen_paths: set[str] = set()
    for entry in baseline.files:
        if not entry.relative_path:
            raise BaselineValidationError("Baseline contains a file entry with no path.")
        if entry.relative_path in seen_paths:
            raise BaselineValidationError(f"Baseline contains a duplicate path: {entry.relative_path!r}")
        seen_paths.add(entry.relative_path)

        if not isinstance(entry.sha256, str) or len(entry.sha256) != _SHA256_HEX_LENGTH:
            raise BaselineValidationError(
                f"Baseline entry {entry.relative_path!r} has an invalid SHA-256 hash."
            )
        if not isinstance(entry.size, int) or entry.size < 0:
            raise BaselineValidationError(f"Baseline entry {entry.relative_path!r} has an invalid size.")
        if not isinstance(entry.modified_time, (int, float)) or entry.modified_time < 0:
            raise BaselineValidationError(
                f"Baseline entry {entry.relative_path!r} has an invalid modified_time."
            )
