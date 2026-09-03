"""Recursive filesystem enumeration for SentinelLite.

Per PROJECT_SPEC.md section 8:
    - The scanner recursively traverses the selected directory.
    - Only files are recorded; directories do not need hashes (8.1).
    - Symbolic links are not recursively followed by default (8.2): this
      module has not determined that following them is safe (it risks
      symlink cycles and silently pulling files from outside the monitored
      directory into the baseline), so `os.walk` is run with
      ``followlinks=False`` unless a caller explicitly opts in. A symlink
      that points at a *file* is still enumerated as a regular directory
      entry (matching normal `os.walk`/`os.scandir` behavior) -- it is only
      symlinked *directories* that are not descended into.
    - A permission error (or any other OS-level access error) on a file or
      directory must not terminate the entire scan (8.3); it is logged and
      surfaced to the caller instead.

This module performs no GUI or storage work -- it only enumerates files and
turns them into `FileRecord` objects using `core.hasher`.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable, Iterator, Optional

from config import DEFAULT_HASH_CHUNK_SIZE
from core.hasher import calculate_sha256
from core.models import FileAccessError, FileRecord

logger = logging.getLogger(__name__)

OnWalkError = Callable[[OSError], None]


def _log_walk_error(error: OSError) -> None:
    logger.warning("Could not access %s: %s", error.filename or error, error)


def enumerate_files(
    root: Path,
    *,
    follow_symlinks: bool = False,
    onerror: Optional[OnWalkError] = None,
) -> Iterator[Path]:
    """Recursively yield every file under ``root``.

    Directories that cannot be listed (e.g. permission denied) are skipped
    rather than aborting the walk; ``onerror`` (defaulting to a logging
    callback) is invoked for each one so the caller can be informed.

    Args:
        root: Directory to walk.
        follow_symlinks: Whether to descend into symlinked directories.
            Defaults to ``False`` -- see module docstring / section 8.2.
        onerror: Called with the ``OSError`` for any directory that could
            not be listed. Defaults to logging a warning.

    Yields:
        Absolute paths (``root`` joined with the walked path) of each file.
    """
    root = Path(root)
    walk_onerror = onerror if onerror is not None else _log_walk_error

    for dirpath, _dirnames, filenames in os.walk(
        root, onerror=walk_onerror, followlinks=follow_symlinks
    ):
        for filename in filenames:
            yield Path(dirpath) / filename


def _relative_path(path: Path, root: Path) -> str:
    """Return ``path`` relative to ``root`` using forward slashes, falling
    back to the raw path string if it is not actually under ``root``
    (e.g. when reported via an `os.walk` error callback)."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def build_file_records(
    root: Path,
    *,
    chunk_size: int = DEFAULT_HASH_CHUNK_SIZE,
    follow_symlinks: bool = False,
) -> tuple[list[FileRecord], list[FileAccessError]]:
    """Enumerate and hash every file under ``root``, producing `FileRecord`s.

    Every file that can be read is hashed with SHA-256 (`core.hasher`,
    incrementally, in ``chunk_size`` chunks). A file that cannot be
    enumerated or hashed (permission denied, disappears mid-scan, etc.)
    does not abort the run: it is logged and returned in the second list
    instead, per PROJECT_SPEC.md sections 7.3 and 8.3.

    Args:
        root: Directory to scan.
        chunk_size: Chunk size (bytes) used for hashing each file.
        follow_symlinks: Whether to descend into symlinked directories.

    Returns:
        A ``(records, errors)`` tuple: successfully hashed files, and files
        that could not be read.
    """
    root = Path(root)
    records: list[FileRecord] = []
    errors: list[FileAccessError] = []

    def record_walk_error(error: OSError) -> None:
        path = Path(error.filename) if error.filename else root
        _log_walk_error(error)
        errors.append(FileAccessError(path=_relative_path(path, root), message=str(error)))

    for file_path in enumerate_files(
        root, follow_symlinks=follow_symlinks, onerror=record_walk_error
    ):
        relative_path = _relative_path(file_path, root)
        try:
            stat_result = file_path.stat()
            sha256 = calculate_sha256(file_path, chunk_size=chunk_size)
        except OSError as exc:
            logger.warning("Could not read file %s: %s", file_path, exc)
            errors.append(FileAccessError(path=relative_path, message=str(exc)))
            continue

        records.append(
            FileRecord(
                path=relative_path,
                sha256=sha256,
                size=stat_result.st_size,
                modified_time=stat_result.st_mtime,
            )
        )

    return records, errors
