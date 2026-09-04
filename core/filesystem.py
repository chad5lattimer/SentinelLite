"""Recursive filesystem enumeration and file-record collection
(PROJECT_SPEC.md section 8).

Responsibilities:
    - Recursively walk a monitored root directory.
    - Skip symbolic links rather than following them (section 8.2).
    - Hash every readable file and produce ``FileRecord`` objects.
    - Continue past permission errors and other per-file/per-directory
      access failures rather than aborting the whole walk (section 8.3),
      recording them as ``FileAccessError`` instead.

This module contains no GUI code; it is used by ``core.baseline`` and
``core.scanner`` in later runs.

Symbolic link policy (section 8.2): SentinelLite does not follow symbolic
links, for either directories or individual files. Following a symlink
could take the scan outside the directory the user selected to monitor, or
into a loop, neither of which is safe or expected for a file-integrity
tool. Symlinks are logged and skipped rather than hashed or reported as
errors.
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


def _log_walk_error(error: OSError) -> None:
    """``os.walk`` error callback: log and continue (section 8.3)."""
    logger.warning("Could not list directory %s: %s", error.filename, error)


def enumerate_files(root: Path) -> Iterator[Path]:
    """Recursively yield every regular file under ``root``.

    Symbolic links (files and directories) are skipped -- see the module
    docstring. Directories that cannot be listed (permission errors) are
    logged and skipped; the walk continues with the remaining directories.
    """
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False, onerror=_log_walk_error):
        current_dir = Path(dirpath)

        # Do not descend into symlinked subdirectories, even though
        # followlinks=False already keeps os.walk from recursing through
        # them; filtering dirnames also keeps them out of this directory's
        # own listing for clarity.
        dirnames[:] = [name for name in dirnames if not (current_dir / name).is_symlink()]

        for name in filenames:
            file_path = current_dir / name
            if file_path.is_symlink():
                logger.info("Skipping symbolic link: %s", file_path)
                continue
            yield file_path


def build_file_record(
    root: Path,
    file_path: Path,
    chunk_size: int = DEFAULT_HASH_CHUNK_SIZE,
) -> FileRecord:
    """Hash ``file_path`` and return a ``FileRecord`` with a path relative
    to ``root``.

    May raise ``OSError`` if the file cannot be read (e.g. it was deleted
    or became inaccessible after enumeration, or a permission error).
    Callers that want to continue past such errors should catch ``OSError``
    (see ``scan_directory``).
    """
    stat_result = file_path.stat()
    digest = calculate_sha256(file_path, chunk_size)
    relative_path = file_path.relative_to(root).as_posix()
    return FileRecord(
        path=relative_path,
        sha256=digest,
        size=stat_result.st_size,
        modified_time=stat_result.st_mtime,
    )


def scan_directory(
    root: Path,
    chunk_size: int = DEFAULT_HASH_CHUNK_SIZE,
) -> tuple[list[FileRecord], list[FileAccessError]]:
    """Enumerate and hash every file under ``root``.

    Returns ``(records, errors)``. A file that cannot be read does not
    abort the scan (PROJECT_SPEC.md section 7.3/8.3): it is logged and
    added to ``errors`` instead, and enumeration continues with the
    remaining files.
    """
    root = Path(root)
    records: list[FileRecord] = []
    errors: list[FileAccessError] = []

    for file_path in enumerate_files(root):
        try:
            records.append(build_file_record(root, file_path, chunk_size))
        except OSError as exc:
            relative_path = _safe_relative_path(root, file_path)
            logger.warning("Could not read file %s: %s", file_path, exc)
            errors.append(FileAccessError(path=relative_path, error=str(exc)))

    return records, errors


def _safe_relative_path(root: Path, file_path: Path) -> str:
    """Best-effort relative path for error reporting; falls back to the
    absolute path if ``file_path`` is not (or is no longer) under ``root``.
    """
    try:
        return file_path.relative_to(root).as_posix()
    except ValueError:
        return str(file_path)
