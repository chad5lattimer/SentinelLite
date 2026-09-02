"""Filesystem enumeration for SentinelLite.

Implements PROJECT_SPEC.md section 8: recursive directory traversal that
turns every readable file under a monitored directory into a
``FileRecord`` (path, hash, size, modified time), while tolerating
per-file and per-directory errors without aborting the walk (sections
7.3 and 8.3) -- a scan should finish and report what it could not read,
never crash.

Symbolic links (section 8.2): this module does not follow symlinks,
either to directories or to files. Following symlinked directories
risks infinite loops and can silently pull content from outside the
monitored directory into the baseline; the MVP avoids that entirely
rather than trying to detect safe cases. A symlink is logged and
skipped -- it is not hashed and does not appear as a hashing ERROR,
since nothing was actually unreadable.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from core.hasher import calculate_sha256
from core.models import FileRecord

logger = logging.getLogger(__name__)

__all__ = [
    "FileAccessError",
    "EnumerationResult",
    "iter_file_paths",
    "build_file_records",
]


@dataclass(frozen=True)
class FileAccessError:
    """Records a single file that could not be hashed.

    ``path`` is relative to the enumerated root, matching
    ``FileRecord.path``, so callers can present errors alongside results.
    """

    path: str
    message: str


@dataclass(frozen=True)
class EnumerationResult:
    """The outcome of walking a directory tree: every file that was
    successfully hashed, plus every file that was not."""

    records: list[FileRecord] = field(default_factory=list)
    errors: list[FileAccessError] = field(default_factory=list)


def _on_walk_error(error: OSError) -> None:
    """os.walk() error callback: log and continue rather than raise,
    per PROJECT_SPEC.md section 8.3 (permission errors must not
    terminate the entire scan)."""
    logger.warning("Permission error while enumerating filesystem: %s", error)


def iter_file_paths(root: Path) -> Iterator[Path]:
    """Yield every regular file under ``root``, recursively.

    Symbolic links are never followed (section 8.2): symlinked
    directories are pruned before descending into them, and symlinked
    files are skipped. Directories that cannot be listed are skipped
    with a logged warning instead of raising (section 8.3).
    """
    for dirpath, dirnames, filenames in os.walk(root, onerror=_on_walk_error, followlinks=False):
        dir_path = Path(dirpath)

        # os.walk(followlinks=False) still lists symlinked directories in
        # dirnames without descending into them by default; prune them
        # explicitly so no ambiguity depends on os.walk internals.
        dirnames[:] = [name for name in dirnames if not (dir_path / name).is_symlink()]

        for name in filenames:
            file_path = dir_path / name
            if file_path.is_symlink():
                logger.warning("Skipping symbolic link (not followed): %s", file_path)
                continue
            yield file_path


def build_file_records(root: Path, chunk_size: int | None = None) -> EnumerationResult:
    """Recursively enumerate ``root`` and hash every readable file.

    Returns an ``EnumerationResult`` with a ``FileRecord`` for every file
    that could be read and hashed, and a ``FileAccessError`` for every
    file that could not (e.g. permission denied, removed mid-scan) --
    such failures are logged and skipped, never raised, so one bad file
    cannot abort enumeration of the rest (PROJECT_SPEC.md section 7.3).

    ``FileRecord.path`` is the file's path relative to ``root``, written
    with forward slashes so it is portable across platforms and stable
    for use as a baseline key in Run 3.
    """
    if chunk_size is None:
        from config import DEFAULT_HASH_CHUNK_SIZE

        chunk_size = DEFAULT_HASH_CHUNK_SIZE

    root = Path(root)
    result = EnumerationResult()

    for file_path in iter_file_paths(root):
        relative_path = file_path.relative_to(root).as_posix()
        try:
            stat_result = file_path.stat()
            digest = calculate_sha256(file_path, chunk_size=chunk_size)
        except OSError as exc:
            logger.warning("Could not read file %s: %s", file_path, exc)
            result.errors.append(FileAccessError(path=relative_path, message=str(exc)))
            continue

        result.records.append(
            FileRecord(
                path=relative_path,
                sha256=digest,
                size=stat_result.st_size,
                modified_time=stat_result.st_mtime,
            )
        )

    return result
