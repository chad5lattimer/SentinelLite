"""Recursive filesystem enumeration for SentinelLite.

Implements PROJECT_SPEC.md section 8 (Filesystem Scanning): recursive
directory traversal, symbolic-link handling, and permission-error
handling that never aborts the overall scan.

This module builds ``FileRecord``/``FileAccessError`` objects (see
core/models.py) by combining filesystem metadata with hashes from
core/hasher.py. It contains no baseline-comparison or GUI logic.
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

#: Called after each file is processed: (processed_count, total_count, relative_path).
ProgressCallback = Callable[[int, int, str], None]


def enumerate_files(root: Path, *, follow_symlinks: bool = False) -> Iterator[Path]:
    """Recursively yield every regular file under ``root``.

    Symbolic links (both files and directories) are skipped by default.
    PROJECT_SPEC.md section 8.2 requires the MVP to avoid recursively
    following symlinks unless explicitly determined to be safe; SentinelLite
    has not made that determination, so symlinks are never followed here.
    This also avoids escaping the monitored directory tree and avoids
    double-hashing files reachable through more than one symlinked path.

    Directories that cannot be listed (e.g. permission denied) are logged
    and skipped rather than aborting the walk (PROJECT_SPEC.md section
    8.3: permission errors must not terminate the entire scan).
    """

    def _on_walk_error(error: OSError) -> None:
        logger.warning("Could not list directory %r: %s", error.filename, error)

    for dirpath, dirnames, filenames in os.walk(
        root, onerror=_on_walk_error, followlinks=follow_symlinks
    ):
        current_dir = Path(dirpath)

        if not follow_symlinks:
            # Prune symlinked subdirectories in-place so os.walk does not
            # descend into them.
            dirnames[:] = [name for name in dirnames if not (current_dir / name).is_symlink()]

        for filename in filenames:
            file_path = current_dir / filename
            if not follow_symlinks and file_path.is_symlink():
                continue
            yield file_path


def build_file_record(
    root: Path, file_path: Path, chunk_size: int = DEFAULT_HASH_CHUNK_SIZE
) -> FileRecord:
    """Hash and stat a single file, returning its ``FileRecord``.

    ``file_path`` must be a descendant of ``root``. The record's ``path``
    is stored relative to ``root`` using forward slashes, per
    PROJECT_SPEC.md section 6.2. Raises ``OSError`` if the file cannot be
    read or stat'd -- callers should catch this (see ``scan_directory``)
    and record it as a ``FileAccessError`` instead of letting it propagate.
    """
    relative_path = file_path.relative_to(root).as_posix()
    stat_result = file_path.stat()
    sha256 = calculate_sha256(file_path, chunk_size=chunk_size)
    return FileRecord(
        path=relative_path,
        sha256=sha256,
        size=stat_result.st_size,
        modified_time=stat_result.st_mtime,
    )


def _friendly_access_error(file_path: Path, error: OSError) -> str:
    """Turn an OSError into the user-friendly message from
    PROJECT_SPEC.md section 18 ("Unable to read file ...")."""
    return f"Unable to read file: {file_path}"


def scan_directory(
    root: Path,
    chunk_size: int = DEFAULT_HASH_CHUNK_SIZE,
    progress_callback: ProgressCallback | None = None,
) -> tuple[list[FileRecord], list[FileAccessError]]:
    """Enumerate and hash every file under ``root``.

    Returns ``(records, errors)``. Files that cannot be read (permission
    errors, files removed mid-scan, etc.) are collected as
    ``FileAccessError`` entries and logged, rather than aborting the scan
    (PROJECT_SPEC.md section 7.3 / 8.3). If ``progress_callback`` is given,
    it is invoked after each file is processed (success or error) with
    ``(processed_count, total_count, relative_path_or_name)``.
    """
    root = Path(root)
    file_paths = list(enumerate_files(root))
    total = len(file_paths)

    records: list[FileRecord] = []
    errors: list[FileAccessError] = []

    for index, file_path in enumerate(file_paths, start=1):
        try:
            record = build_file_record(root, file_path, chunk_size=chunk_size)
        except OSError as error:
            message = _friendly_access_error(file_path, error)
            logger.warning("%s (%s)", message, error)
            try:
                relative_path = file_path.relative_to(root).as_posix()
            except ValueError:
                relative_path = str(file_path)
            errors.append(FileAccessError(path=relative_path, message=message))
            if progress_callback is not None:
                progress_callback(index, total, relative_path)
            continue

        records.append(record)
        if progress_callback is not None:
            progress_callback(index, total, record.path)

    return records, errors
