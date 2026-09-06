"""Recursive filesystem enumeration for SentinelLite.

Walks a monitored directory, hashes each readable file, and produces
``FileRecord`` objects (PROJECT_SPEC.md sections 6.1 and 8).

Design decisions (documented per section 37, "if a requirement is
ambiguous, document the decision"):

- Permission errors on individual files or directories do not abort
  enumeration (sections 7.3 and 8.3): they are logged and returned as
  ``FileError`` entries so the caller can inform the user after the scan
  completes, without crashing.
- Symbolic links are never followed (section 8.2). This avoids symlink
  cycles and prevents files outside the monitored directory from being
  silently pulled into the baseline. Encountered symlinks are skipped
  and logged at debug level.
- Only regular files are hashed; directories themselves are not
  recorded (section 8.1).

This module contains no GUI code, per PROJECT_SPEC.md section 5.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from config import DEFAULT_HASH_CHUNK_SIZE
from core.hasher import HashError, calculate_sha256
from core.models import FileRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FileError:
    """A file or directory that could not be read during enumeration."""

    path: str
    message: str


@dataclass(frozen=True)
class EnumerationResult:
    """The outcome of enumerating and hashing a directory tree."""

    records: list[FileRecord] = field(default_factory=list)
    errors: list[FileError] = field(default_factory=list)


def enumerate_files(
    root_directory: Path,
    chunk_size: int = DEFAULT_HASH_CHUNK_SIZE,
) -> EnumerationResult:
    """Recursively enumerate and hash every regular file under ``root_directory``.

    Args:
        root_directory: The directory to scan. Must exist and be a
            directory.
        chunk_size: Chunk size (in bytes) used for incremental hashing.

    Returns:
        An ``EnumerationResult`` containing a ``FileRecord`` for every
        successfully hashed file (paths relative to ``root_directory``,
        using forward slashes) and a ``FileError`` for every file or
        directory that could not be processed. Enumeration never raises
        for individual unreadable files/directories; it only raises if
        ``root_directory`` itself is not a usable directory.
    """
    root_directory = Path(root_directory)
    if not root_directory.is_dir():
        raise NotADirectoryError(f"Not a directory: {root_directory}")

    records: list[FileRecord] = []
    errors: list[FileError] = []

    for path in _walk(root_directory, root_directory, errors):
        relative = path.relative_to(root_directory).as_posix()
        try:
            stat_result = path.stat()
        except OSError as exc:
            message = f"Unable to access file: {path}"
            logger.warning("%s (%s)", message, exc)
            errors.append(FileError(path=relative, message=message))
            continue

        try:
            digest = calculate_sha256(path, chunk_size=chunk_size)
        except HashError as exc:
            logger.warning("%s", exc)
            errors.append(FileError(path=relative, message=str(exc)))
            continue

        records.append(
            FileRecord(
                path=relative,
                sha256=digest,
                size=stat_result.st_size,
                modified_time=stat_result.st_mtime,
            )
        )

    return EnumerationResult(records=records, errors=errors)


def _walk(
    directory: Path,
    root_directory: Path,
    errors: list[FileError],
) -> Iterator[Path]:
    """Yield every regular file under ``directory``, recursively.

    Directories that cannot be listed (permission errors) are recorded
    as errors and skipped rather than aborting enumeration. Symbolic
    links -- to files or directories -- are never followed.
    """
    try:
        entries = sorted(directory.iterdir())
    except OSError as exc:
        try:
            relative = directory.relative_to(root_directory).as_posix()
        except ValueError:
            relative = str(directory)
        message = f"Unable to access directory: {directory}"
        logger.warning("%s (%s)", message, exc)
        errors.append(FileError(path=relative, message=message))
        return

    for entry in entries:
        if entry.is_symlink():
            logger.debug("Skipping symbolic link: %s", entry)
            continue
        if entry.is_dir():
            yield from _walk(entry, root_directory, errors)
        elif entry.is_file():
            yield entry
