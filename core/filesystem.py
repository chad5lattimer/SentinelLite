"""Recursive filesystem enumeration and FileRecord collection.

Per PROJECT_SPEC.md section 8:
    - All files under the monitored root are included by default.
    - Symbolic links are not followed (see `iter_files` for the
      documented rationale, per section 8.2).
    - Permission errors must not terminate enumeration or hashing -- they
      are recorded and processing continues (sections 7.3 / 8.3).

This module contains no GUI code (PROJECT_SPEC.md section 5: the GUI must
not contain hashing or filesystem comparison logic, and this is its
converse -- core logic stays free of GUI concerns).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterator, NamedTuple

from config import DEFAULT_HASH_CHUNK_SIZE
from core.hasher import calculate_sha256
from core.models import FileError, FileRecord

logger = logging.getLogger(__name__)


def iter_files(root_dir: Path) -> Iterator[Path]:
    """Recursively yield every regular file under `root_dir`.

    Directories are not yielded themselves -- only files need to be
    recorded (PROJECT_SPEC.md section 8.1).

    Symbolic links are not followed: `os.walk` is called with
    `followlinks=False` so symlinked subdirectories are not descended
    into, and any symlinked file is skipped. This is the documented
    choice for PROJECT_SPEC.md section 8.2 -- it avoids both directory
    cycles and a monitored baseline silently expanding to cover files
    outside the selected root, without needing to track visited inodes.

    Errors listing a directory (e.g. permission denied) are logged and
    that directory is skipped; enumeration of the rest of the tree
    continues (PROJECT_SPEC.md section 8.3).
    """
    root_dir = Path(root_dir)

    def _on_walk_error(error: OSError) -> None:
        logger.warning("Cannot list directory %s: %s", getattr(error, "filename", error), error)

    for current_dir, dirnames, filenames in os.walk(
        root_dir, onerror=_on_walk_error, followlinks=False
    ):
        current_path = Path(current_dir)
        del dirnames  # Not needed: symlinked dirs are already not descended into.

        for filename in filenames:
            file_path = current_path / filename
            if file_path.is_symlink():
                logger.debug("Skipping symbolic link: %s", file_path)
                continue
            yield file_path


class FileCollectionResult(NamedTuple):
    """Outcome of collecting `FileRecord`s for a directory tree."""

    records: list[FileRecord]
    errors: list[FileError]


def collect_file_records(
    root_dir: Path,
    chunk_size: int = DEFAULT_HASH_CHUNK_SIZE,
) -> FileCollectionResult:
    """Recursively enumerate and hash every file under `root_dir`.

    Returns a `FileCollectionResult` with a `FileRecord` for every file
    that was successfully read and hashed, and a `FileError` for every
    file that could not be read (permission denied, removed mid-scan,
    etc). A single unreadable file never aborts the collection
    (PROJECT_SPEC.md sections 7.3 and 8.3) -- errors are logged and
    collection continues with the remaining files.
    """
    root_dir = Path(root_dir)
    records: list[FileRecord] = []
    errors: list[FileError] = []

    for file_path in iter_files(root_dir):
        relative_path = file_path.relative_to(root_dir).as_posix()
        try:
            stat_result = file_path.stat()
            sha256 = calculate_sha256(file_path, chunk_size=chunk_size)
        except OSError as error:
            logger.warning("Could not read file %s: %s", file_path, error)
            errors.append(FileError(path=relative_path, message=str(error)))
            continue

        records.append(
            FileRecord(
                path=relative_path,
                sha256=sha256,
                size=stat_result.st_size,
                modified_time=stat_result.st_mtime,
            )
        )

    return FileCollectionResult(records=records, errors=errors)
