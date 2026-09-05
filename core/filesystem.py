"""Recursive filesystem enumeration and hashing for SentinelLite.

Walks a monitored directory tree, hashes every readable file, and produces
``FileRecord`` objects (PROJECT_SPEC.md section 6.1). Files and directories
that cannot be processed are reported as ``FileError`` objects rather than
raising -- enumeration always continues, per PROJECT_SPEC.md sections 7.3
and 8.3.

Symbolic links (PROJECT_SPEC.md section 8.2): SentinelLite does not follow
symbolic links, for either files or directories. A symlinked directory is
not descended into, and a symlinked file is skipped entirely (it is not
recorded as a ``FileRecord`` or a ``FileError``). This avoids escaping the
monitored root and avoids symlink cycles, at the cost of not monitoring the
link targets themselves -- an acceptable and documented MVP limitation.

This module contains no GUI code and no direct database access; it is pure
filesystem/hashing logic, consumed by the baseline and scan engines in
later runs.
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


class EnumerationResult(NamedTuple):
    """The outcome of walking and hashing a directory tree."""

    records: list[FileRecord]
    errors: list[FileError]


def _relative_path(path: Path, root: Path) -> str:
    """Return ``path`` relative to ``root`` using forward slashes.

    Falls back to the raw string form if ``path`` is not actually inside
    ``root`` (this should not normally happen, but directory-listing errors
    can report paths in unexpected forms).
    """
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _iter_candidate_files(root: Path, errors: list[FileError]) -> Iterator[Path]:
    """Yield every non-symlink file under ``root``, recursively.

    Directory-listing failures (e.g. permission denied) are recorded as
    ``FileError`` entries and do not stop the walk of sibling directories.
    """

    def _on_walk_error(exc: OSError) -> None:
        failed_path = Path(exc.filename) if exc.filename else root
        logger.warning("Could not list directory %s: %s", failed_path, exc)
        errors.append(FileError(path=_relative_path(failed_path, root), message=str(exc)))

    for dirpath, dirnames, filenames in os.walk(root, onerror=_on_walk_error, followlinks=False):
        current_dir = Path(dirpath)

        # os.walk(followlinks=False) already avoids descending *into*
        # symlinked directories, but it still lists them in dirnames. Drop
        # them explicitly so behavior is obvious and doesn't rely on that
        # implementation detail.
        dirnames[:] = [name for name in dirnames if not (current_dir / name).is_symlink()]

        for filename in filenames:
            file_path = current_dir / filename
            if file_path.is_symlink():
                continue
            yield file_path


def enumerate_and_hash(
    root_directory: Path | str,
    chunk_size: int = DEFAULT_HASH_CHUNK_SIZE,
) -> EnumerationResult:
    """Recursively enumerate and hash every readable file under a directory.

    Args:
        root_directory: The directory to scan (monitored root).
        chunk_size: Chunk size in bytes used for incremental hashing.

    Returns:
        An ``EnumerationResult`` containing a ``FileRecord`` for every file
        that could be stat'd and hashed successfully, and a ``FileError``
        for every file or directory that could not be (PROJECT_SPEC.md
        section 7.3: continue processing, do not crash the scan).
    """
    root = Path(root_directory)
    records: list[FileRecord] = []
    errors: list[FileError] = []

    for file_path in _iter_candidate_files(root, errors):
        relative_path = _relative_path(file_path, root)
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

    return EnumerationResult(records=records, errors=errors)
