"""Recursive filesystem enumeration and hashing (PROJECT_SPEC.md section 8).

This module walks a monitored directory, hashes every readable file, and
produces `FileRecord`/`FileAccessError` objects. It contains no baseline
comparison or GUI logic -- it is the shared engine used by both baseline
creation (Run 3) and scanning (Run 4).

Symbolic links (section 8.2): SentinelLite does not follow symbolic links
by default, for both directories and files. Following symlinks could walk
outside the monitored directory or loop indefinitely, and hashing a
symlink's target does not represent the integrity of the monitored
directory itself. This is a deliberate, documented decision, not an
oversight; ``follow_symlinks=True`` is available for callers that have
determined it is safe for their use case.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterator
from pathlib import Path

from config import DEFAULT_HASH_CHUNK_SIZE
from core.hasher import calculate_sha256
from core.models import FileAccessError, FileRecord

logger = logging.getLogger(__name__)

#: Called as (files_processed, total_files, current_relative_path) while a
#: directory is being hashed, so a caller (e.g. the GUI) can display
#: progress (PROJECT_SPEC.md section 13). ``total_files`` is a snapshot
#: taken before hashing begins and may become stale if the filesystem
#: changes concurrently -- the spec explicitly allows an approximate
#: progress calculation.
ProgressCallback = Callable[[int, int, str], None]


def iter_files(root: Path, follow_symlinks: bool = False) -> Iterator[Path]:
    """Recursively yield every regular file under ``root``.

    Directories and files that are symbolic links are skipped unless
    ``follow_symlinks`` is True (see module docstring). Files that
    disappear between being listed and being visited (e.g. deleted mid-walk)
    are silently skipped by ``os.walk`` semantics; that race is handled
    again, safely, when the caller attempts to hash the file.
    """
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        dirpath_obj = Path(dirpath)

        if not follow_symlinks:
            # Prune symlinked subdirectories in-place so os.walk does not
            # descend into them.
            dirnames[:] = [
                name for name in dirnames if not (dirpath_obj / name).is_symlink()
            ]

        for filename in filenames:
            file_path = dirpath_obj / filename
            if not follow_symlinks and file_path.is_symlink():
                continue
            yield file_path


def enumerate_and_hash(
    root: Path,
    chunk_size: int = DEFAULT_HASH_CHUNK_SIZE,
    follow_symlinks: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> tuple[list[FileRecord], list[FileAccessError]]:
    """Recursively enumerate and hash every file under ``root``.

    Returns a ``(records, errors)`` tuple:
        - ``records``: a `FileRecord` for every file that was read and
          hashed successfully.
        - ``errors``: a `FileAccessError` for every file that could not be
          read (permission denied, deleted mid-scan, I/O error, etc).

    A file that cannot be read never raises out of this function and never
    stops the remaining files from being processed (PROJECT_SPEC.md
    sections 7.3 and 8.3).
    """
    root = Path(root)
    files = sorted(iter_files(root, follow_symlinks=follow_symlinks))
    total = len(files)

    records: list[FileRecord] = []
    errors: list[FileAccessError] = []

    for index, file_path in enumerate(files, start=1):
        relative_path = file_path.relative_to(root).as_posix()

        try:
            stat_result = file_path.stat()
            digest = calculate_sha256(file_path, chunk_size=chunk_size)
        except OSError as exc:
            logger.warning("Could not read file %s: %s", relative_path, exc)
            errors.append(FileAccessError(path=relative_path, message=str(exc)))
        else:
            records.append(
                FileRecord(
                    path=relative_path,
                    sha256=digest,
                    size=stat_result.st_size,
                    modified_time=stat_result.st_mtime,
                )
            )

        if progress_callback is not None:
            progress_callback(index, total, relative_path)

    return records, errors
