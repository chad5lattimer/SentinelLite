"""Recursive filesystem enumeration and metadata collection
(PROJECT_SPEC.md section 8).

This module walks a monitored directory, hashes every readable file, and
produces `FileRecord` objects for use by the baseline and scan engines
(implemented in later runs). It intentionally contains no baseline or
comparison logic, and no GUI code -- only filesystem traversal and
hashing, matching the layered architecture in PROJECT_SPEC.md section 5.

Symbolic links (PROJECT_SPEC.md section 8.2): SentinelLite does not
follow symbolic links, whether they point to files or directories.
Following them could walk outside the monitored directory, revisit the
same files through multiple paths, or loop indefinitely on a cycle --
none of which the MVP tries to reason about safely. A symlink is
therefore always skipped (and logged), never hashed or recursed into.

Permission errors (PROJECT_SPEC.md section 8.3): a directory or file
that cannot be accessed is logged and skipped; it never aborts the
overall scan.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

from config import DEFAULT_HASH_CHUNK_SIZE
from core.hasher import calculate_sha256
from core.models import FileError, FileRecord

logger = logging.getLogger(__name__)


def enumerate_files(root: Path) -> Iterator[Path]:
    """Recursively yield every regular file under ``root``.

    Symbolic links are never followed (see module docstring). A
    directory that cannot be listed, or an entry whose type cannot be
    determined (e.g. a permission error on `stat`), is logged and
    skipped rather than raised.
    """
    try:
        entries = sorted(Path(root).iterdir(), key=lambda entry: entry.name)
    except OSError as exc:
        logger.warning("Cannot list directory %s: %s", root, exc)
        return

    for entry in entries:
        try:
            if entry.is_symlink():
                logger.info("Skipping symbolic link: %s", entry)
                continue
            if entry.is_dir():
                yield from enumerate_files(entry)
            elif entry.is_file():
                yield entry
        except OSError as exc:
            logger.warning("Cannot access %s: %s", entry, exc)
            continue


def scan_directory(
    root: Path,
    chunk_size: int = DEFAULT_HASH_CHUNK_SIZE,
) -> tuple[list[FileRecord], list[FileError]]:
    """Enumerate and hash every readable file under ``root``.

    Returns a ``(records, errors)`` tuple. Each `FileRecord.path` is
    relative to ``root`` (forward-slash separated). A file that cannot be
    read -- permission denied, deleted mid-scan, etc. -- is reported as a
    `FileError` instead of raising, so the remaining files are still
    processed (PROJECT_SPEC.md sections 7.3 and 8.3).
    """
    root = Path(root)
    records: list[FileRecord] = []
    errors: list[FileError] = []

    for file_path in enumerate_files(root):
        relative_path = file_path.relative_to(root).as_posix()
        try:
            stat_result = file_path.stat()
            digest = calculate_sha256(file_path, chunk_size=chunk_size)
        except OSError as exc:
            logger.warning("Could not read file %s: %s", file_path, exc)
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
