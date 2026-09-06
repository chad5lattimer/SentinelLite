"""Recursive filesystem enumeration for the scan engine (PROJECT_SPEC.md
section 8).

Walks a monitored directory tree, producing a ``FileRecord`` (relative
path, sha256, size, modified_time) for every readable file, and a
``FileError`` for every file that could not be enumerated or hashed.
Permission errors and unreadable files never abort the walk (section
8.3) -- they are logged and recorded, and enumeration continues.

Symbolic links: SentinelLite does not follow symbolic links, either to
files or to directories, while walking the monitored directory. This
avoids infinite loops from symlink cycles and avoids silently hashing
content that lives outside the monitored directory tree. This is the
documented behavior required by section 8.2; it is not currently
configurable in the MVP.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterator

from config import DEFAULT_HASH_CHUNK_SIZE
from core.hasher import calculate_sha256
from core.models import FileError, FileRecord

logger = logging.getLogger(__name__)


def enumerate_files(root: Path) -> Iterator[Path]:
    """Yield every regular file under ``root``, recursively.

    Symbolic links (to files or to directories) are skipped entirely --
    see the module docstring for rationale. Directories that cannot be
    listed (permission errors) are logged and skipped rather than
    aborting the walk.
    """
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(
        root, onerror=_log_walk_error, followlinks=False
    ):
        current_dir = Path(dirpath)

        # Do not descend into symlinked directories, even though
        # followlinks=False already prevents os.walk from recursing
        # through them -- this keeps the intent explicit and protects
        # against platform differences.
        dirnames[:] = [
            name for name in dirnames if not (current_dir / name).is_symlink()
        ]

        for filename in filenames:
            file_path = current_dir / filename
            if file_path.is_symlink():
                continue
            yield file_path


def _log_walk_error(error: OSError) -> None:
    logger.warning("Unable to list directory during scan: %s", error)


def scan_directory(
    root: Path,
    chunk_size: int = DEFAULT_HASH_CHUNK_SIZE,
) -> tuple[list[FileRecord], list[FileError]]:
    """Recursively enumerate and hash every file under ``root``.

    Returns a ``(records, errors)`` tuple. A file that cannot be read or
    hashed (permission errors, files removed mid-scan, etc.) is reported
    as a `FileError` rather than aborting the scan, per section 7.3.

    Paths in the returned records/errors are relative to ``root`` and
    use forward slashes, so baselines remain portable (section 6.2).
    """
    root = Path(root)
    records: list[FileRecord] = []
    errors: list[FileError] = []

    for file_path in enumerate_files(root):
        relative_path = file_path.relative_to(root).as_posix()
        try:
            stat_result = file_path.stat()
            digest = calculate_sha256(file_path, chunk_size)
        except OSError as exc:
            logger.warning("Unable to read file %s: %s", file_path, exc)
            errors.append(FileError(path=relative_path, message=str(exc)))
            continue

        records.append(
            FileRecord(
                path=relative_path,
                sha256=digest,
                size=stat_result.st_size,
                modified_time=stat_result.st_mtime,
            )
        )

    return records, errors
