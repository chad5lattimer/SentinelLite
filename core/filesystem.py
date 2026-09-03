"""Recursive filesystem enumeration and file-record collection.

Per PROJECT_SPEC.md sections 8 and 9: recursively traverse a monitored
directory, hash every readable file, and never let a single inaccessible
file or directory abort the whole scan.

This module contains no GUI code (section 5/35).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from config import DEFAULT_HASH_CHUNK_SIZE
from core.hasher import calculate_sha256
from core.models import FileAccessError, FileRecord

logger = logging.getLogger(__name__)


def iter_files(root: Path, *, follow_symlinks: bool = False) -> Iterator[Path]:
    """Recursively yield every regular file under ``root``.

    Symbolic links -- both directories and files -- are skipped by
    default. This is the documented behavior required by PROJECT_SPEC.md
    section 8.2 ("The MVP should avoid recursively following symbolic
    links unless explicitly determined to be safe"): following directory
    symlinks can walk outside the monitored root or loop forever on a
    cyclic link, and a symlinked file's target is not really "inside" the
    monitored directory. Pass ``follow_symlinks=True`` to opt in; nothing
    in the application does so by default.

    Directories that cannot be listed (permission errors, etc.) are
    logged and skipped rather than raising, per section 8.3.
    """
    root = Path(root)

    def _onerror(exc: OSError) -> None:
        logger.warning("Cannot list directory %s: %s", exc.filename, exc)

    for dirpath, dirnames, filenames in os.walk(
        root, topdown=True, onerror=_onerror, followlinks=follow_symlinks
    ):
        dirpath_path = Path(dirpath)

        if not follow_symlinks:
            # Prune symlinked subdirectories in-place so os.walk does not
            # descend into them.
            dirnames[:] = [
                name for name in dirnames if not (dirpath_path / name).is_symlink()
            ]

        for filename in filenames:
            file_path = dirpath_path / filename
            if not follow_symlinks and file_path.is_symlink():
                continue
            yield file_path


@dataclass
class FilesystemScanResult:
    """The outcome of enumerating and hashing a directory tree."""

    records: list[FileRecord] = field(default_factory=list)
    errors: list[FileAccessError] = field(default_factory=list)


def build_file_records(
    root: Path,
    *,
    chunk_size: int = DEFAULT_HASH_CHUNK_SIZE,
    follow_symlinks: bool = False,
) -> FilesystemScanResult:
    """Enumerate and hash every file under ``root``.

    Returns a ``FilesystemScanResult`` containing a ``FileRecord`` for
    every file that could be read, and a ``FileAccessError`` for every
    file that could not (permission errors, files removed mid-scan,
    broken links, etc.). An inaccessible file is logged and recorded --
    it never aborts enumeration of the remaining files (sections 7.3,
    8.3, 9).
    """
    root = Path(root)
    result = FilesystemScanResult()

    for file_path in iter_files(root, follow_symlinks=follow_symlinks):
        relative_path = file_path.relative_to(root).as_posix()
        try:
            stat_result = file_path.stat()
            sha256 = calculate_sha256(file_path, chunk_size=chunk_size)
        except OSError as exc:
            logger.warning("Unable to read file %s: %s", file_path, exc)
            result.errors.append(FileAccessError(path=relative_path, message=str(exc)))
            continue

        result.records.append(
            FileRecord(
                path=relative_path,
                sha256=sha256,
                size=stat_result.st_size,
                modified_time=stat_result.st_mtime,
            )
        )

    return result
