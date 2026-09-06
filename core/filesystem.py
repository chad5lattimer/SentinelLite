"""Recursive filesystem enumeration for SentinelLite.

Walks a monitored directory, hashing every accessible regular file into a
`FileRecord`. Contains no baseline-comparison or GUI logic -- see
`core.baseline` and `core.scanner` (later runs) for those responsibilities.

Symbolic links (PROJECT_SPEC.md section 8.2):
    SentinelLite does not follow symbolic links, whether they point to
    files or directories. This is a deliberate, documented choice: following
    symlinked directories can create cycles (infinite recursion) or cause
    the same on-disk file to be hashed under multiple baseline paths, both
    of which would make scan results ambiguous. A symlink is therefore
    skipped and logged rather than treated as "safe to follow".

Permission errors (PROJECT_SPEC.md section 8.3):
    A directory that cannot be listed, or a file that cannot be opened for
    hashing, is logged and skipped. It never aborts enumeration of the rest
    of the tree.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterator

from config import DEFAULT_HASH_CHUNK_SIZE
from core.hasher import calculate_sha256
from core.models import FileAccessError, FileRecord

logger = logging.getLogger(__name__)


def enumerate_files(root: Path) -> Iterator[Path]:
    """Recursively yield every regular file under `root`.

    Symbolic links are skipped (see module docstring). Directories that
    raise a permission error while being listed are logged and skipped;
    enumeration continues with the remaining directories.
    """

    def _on_walk_error(error: OSError) -> None:
        logger.warning("Could not list directory %s: %s", error.filename, error)

    for dirpath, dirnames, filenames in os.walk(root, onerror=_on_walk_error, followlinks=False):
        current_dir = Path(dirpath)

        # Do not descend into symlinked directories. Mutating dirnames
        # in place is os.walk's documented way to prune traversal.
        pruned = []
        for name in dirnames:
            if (current_dir / name).is_symlink():
                logger.debug("Skipping symbolic link directory: %s", current_dir / name)
            else:
                pruned.append(name)
        dirnames[:] = pruned

        for filename in filenames:
            file_path = current_dir / filename
            if file_path.is_symlink():
                logger.debug("Skipping symbolic link: %s", file_path)
                continue
            yield file_path


def collect_file_records(
    root: Path,
    chunk_size: int = DEFAULT_HASH_CHUNK_SIZE,
) -> tuple[list[FileRecord], list[FileAccessError]]:
    """Enumerate and hash every accessible file under `root`.

    Returns a `(records, errors)` tuple:
        - `records`: a `FileRecord` for every file that was successfully
          hashed, with `path` relative to `root` (POSIX-style separators).
        - `errors`: a `FileAccessError` for every file that could not be
          read (permission denied, vanished mid-scan, etc). Per
          PROJECT_SPEC.md section 7.3, these do not abort processing.
    """
    root = Path(root)
    records: list[FileRecord] = []
    errors: list[FileAccessError] = []

    for file_path in enumerate_files(root):
        relative_path = file_path.relative_to(root).as_posix()
        try:
            stat_result = file_path.stat()
            digest = calculate_sha256(file_path, chunk_size=chunk_size)
        except OSError as exc:
            logger.warning("Could not read file %s: %s", file_path, exc)
            errors.append(FileAccessError(path=relative_path, message=str(exc)))
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
