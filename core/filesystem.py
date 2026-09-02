"""Recursive filesystem enumeration for SentinelLite.

Walks a monitored directory tree and produces the ``FileRecord``s (and any
``FileError``s) used to build a baseline or run a scan. Per PROJECT_SPEC.md
section 5, this module contains security/core logic only -- it has no
GUI dependencies and must not be imported by anything outside ``core`` /
``storage`` and their tests.

Symbolic link policy (PROJECT_SPEC.md section 8.2)
----------------------------------------------------
By default, SentinelLite does **not** follow symbolic links, for both
directories and files:

    - Symlinked directories are not recursed into, avoiding cycles (e.g. a
      symlink pointing back at an ancestor directory) and avoiding
      monitoring content outside the directory the user actually selected.
    - Symlinked files are skipped entirely rather than hashing whatever
      they currently point at, since that target may live outside the
      monitored directory and may change independently of it.

This is the conservative, safe default. Advanced callers may opt in via
``follow_symlinks=True`` if they have determined it is safe for their use
case; the MVP GUI does not expose this option.

Permission errors (PROJECT_SPEC.md sections 7.3 and 8.3)
----------------------------------------------------------
A directory or file that cannot be accessed does not stop enumeration.
Inaccessible directories are logged and skipped; inaccessible files are
recorded as ``FileError`` entries so the caller can inform the user after
the scan completes, and processing continues with the remaining files.
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


def _on_walk_error(error: OSError) -> None:
    """Called by ``os.walk`` when a directory cannot be listed.

    Logs the failure and lets the walk continue with the remaining
    directories -- a permission error on one subdirectory must not abort
    the whole enumeration (PROJECT_SPEC.md section 8.3).
    """
    logger.warning("Could not access directory during scan: %s", error)


def iter_file_paths(root: Path, *, follow_symlinks: bool = False) -> Iterator[Path]:
    """Yield every regular file under ``root``, recursively.

    See the module docstring for the symlink policy. Directories that
    cannot be listed are skipped (and logged); the walk continues.
    """
    for dirpath, _dirnames, filenames in os.walk(
        root, onerror=_on_walk_error, followlinks=follow_symlinks
    ):
        dir_path = Path(dirpath)
        for filename in filenames:
            file_path = dir_path / filename
            if not follow_symlinks and file_path.is_symlink():
                continue
            yield file_path


def collect_file_records(
    root: Path,
    *,
    chunk_size: int = DEFAULT_HASH_CHUNK_SIZE,
    follow_symlinks: bool = False,
) -> tuple[list[FileRecord], list[FileError]]:
    """Enumerate and hash every file under ``root``.

    Returns ``(records, errors)``: a ``FileRecord`` for every file that
    could be stat'd and hashed successfully, and a ``FileError`` for every
    file that could not be read (permission denied, removed mid-scan,
    etc.). A file that fails does not prevent the remaining files from
    being processed (PROJECT_SPEC.md section 7.3).

    Paths are recorded relative to ``root``, using forward slashes, so
    baselines remain portable (PROJECT_SPEC.md section 6.2).
    """
    root = Path(root)
    records: list[FileRecord] = []
    errors: list[FileError] = []

    for file_path in iter_file_paths(root, follow_symlinks=follow_symlinks):
        relative_path = file_path.relative_to(root).as_posix()
        try:
            stat_result = file_path.stat()
            sha256 = calculate_sha256(file_path, chunk_size=chunk_size)
        except OSError as exc:
            logger.warning("Could not read file %s: %s", relative_path, exc)
            errors.append(FileError(path=relative_path, message=str(exc)))
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
