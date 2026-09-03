"""Filesystem enumeration and file-record collection for SentinelLite.

Per PROJECT_SPEC.md sections 7, 8, and 27 (Run 2), this module:
    - Recursively enumerates files under a monitored root directory.
    - Hashes each readable file (via core.hasher) and returns FileRecord
      objects (core.models) using relative, slash-normalized paths.
    - Handles inaccessible files/directories gracefully: a permission
      error or unreadable file is recorded as a FileError and scanning
      continues with the remaining files (section 7.3, 8.3).

Symbolic link policy (section 8.2)
-----------------------------------
By default, SentinelLite does NOT follow symbolic links, for either
directories or files. A directory symlink could point outside the
monitored root (or create a cycle), and a file symlink could silently
hash content that lives outside the monitored tree. Both are skipped
during enumeration rather than followed. This is the safe default; it can
be overridden via ``follow_symlinks=True`` for callers that have
explicitly determined it is safe to do so, as the spec allows.

This module contains no GUI code and does not depend on the GUI layer.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable, Iterator

from config import DEFAULT_HASH_CHUNK_SIZE
from core.hasher import calculate_sha256
from core.models import FileError, FileRecord

logger = logging.getLogger(__name__)

#: Called as (files_processed, files_total, current_relative_path) while
#: scan_directory hashes files, so the GUI can display progress without
#: this module knowing anything about the GUI (PROJECT_SPEC.md section 13).
ProgressCallback = Callable[[int, int, str], None]


def _to_relative_posix(root: Path, file_path: Path) -> str:
    """Return ``file_path`` relative to ``root`` using forward slashes,
    per the portable path convention in PROJECT_SPEC.md section 6.2."""
    return file_path.relative_to(root).as_posix()


def iter_files(root: Path, follow_symlinks: bool = False) -> Iterator[Path]:
    """Recursively yield every regular file under ``root``.

    Directories that cannot be listed (permission errors) are logged and
    skipped rather than aborting the whole walk (section 8.3). Symbolic
    links (directories and files) are skipped by default -- see the
    module docstring.
    """
    root = Path(root)

    def _on_walk_error(error: OSError) -> None:
        logger.warning("Cannot access directory during scan: %s (%s)", error.filename, error)

    for dirpath, dirnames, filenames in os.walk(
        root, onerror=_on_walk_error, followlinks=follow_symlinks
    ):
        current_dir = Path(dirpath)

        if not follow_symlinks:
            # Prune symlinked subdirectories in-place so os.walk does not
            # descend into them.
            dirnames[:] = [
                name for name in dirnames if not (current_dir / name).is_symlink()
            ]

        for filename in filenames:
            file_path = current_dir / filename
            if not follow_symlinks and file_path.is_symlink():
                logger.info("Skipping symbolic link (not followed): %s", file_path)
                continue
            yield file_path


def build_file_record(
    root: Path, file_path: Path, chunk_size: int = DEFAULT_HASH_CHUNK_SIZE
) -> FileRecord:
    """Hash a single file and return its FileRecord.

    Raises ``OSError`` if the file cannot be read; callers scanning many
    files should catch this per file (see ``scan_directory``) rather than
    letting one unreadable file abort the whole operation.
    """
    stat_result = file_path.stat()
    sha256 = calculate_sha256(file_path, chunk_size=chunk_size)
    return FileRecord(
        path=_to_relative_posix(root, file_path),
        sha256=sha256,
        size=stat_result.st_size,
        modified_time=stat_result.st_mtime,
    )


def scan_directory(
    root: Path,
    chunk_size: int = DEFAULT_HASH_CHUNK_SIZE,
    follow_symlinks: bool = False,
    on_progress: ProgressCallback | None = None,
) -> tuple[list[FileRecord], list[FileError]]:
    """Enumerate and hash every readable file under ``root``.

    Returns ``(records, errors)``. Files that cannot be read (permission
    errors, files removed mid-scan, etc.) are recorded in ``errors``
    rather than raising, so a single bad file never aborts the scan
    (PROJECT_SPEC.md sections 7.3 and 8.3).
    """
    root = Path(root)
    file_paths = list(iter_files(root, follow_symlinks=follow_symlinks))
    total = len(file_paths)

    records: list[FileRecord] = []
    errors: list[FileError] = []

    for processed, file_path in enumerate(file_paths, start=1):
        relative_path = _to_relative_posix(root, file_path)
        if on_progress is not None:
            on_progress(processed, total, relative_path)

        try:
            records.append(build_file_record(root, file_path, chunk_size=chunk_size))
        except OSError as exc:
            logger.warning("Unable to read file during scan: %s (%s)", file_path, exc)
            errors.append(FileError(path=relative_path, message=str(exc)))

    return records, errors
