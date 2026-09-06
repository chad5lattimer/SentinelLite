"""Recursive filesystem enumeration and file-record construction.

Per PROJECT_SPEC.md section 8, the scanner must recursively traverse the
selected directory, include all files by default, avoid recursively
following symbolic links, and never let a permission error abort the
entire walk.

This module contains no GUI code and no baseline/scan-comparison logic --
those arrive in later runs (`core/baseline.py`, `core/scanner.py`). It
only knows how to walk a directory and turn what it finds into
`FileRecord` / `FileAccessError` objects.
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


def _to_relative_posix(path: Path, root: Path) -> str:
    """Return ``path`` relative to ``root`` using forward slashes.

    Baselines store relative, forward-slash paths (PROJECT_SPEC.md
    section 6.2) so they remain portable across OSes and if the monitored
    directory is moved or accessed via a different drive letter/mount
    point.
    """
    return path.relative_to(root).as_posix()


def iter_files(root: Path, follow_symlinks: bool = False) -> Iterator[Path]:
    """Recursively yield every regular file under ``root``.

    Design decision (PROJECT_SPEC.md section 8.2): symbolic links are
    skipped by default -- both symlinked files and symlinked directories.
    Following symlinked directories risks infinite loops (a link pointing
    back into an ancestor) and could silently pull files from outside the
    monitored directory into the baseline/scan, which would be a
    surprising trust boundary for a file-integrity tool. Pass
    ``follow_symlinks=True`` only when that behavior has been explicitly
    determined to be safe for the caller's use case.

    Directories that cannot be listed (permission errors) are logged and
    skipped rather than aborting the walk, per section 8.3.
    """
    root = Path(root)

    def _on_walk_error(error: OSError) -> None:
        logger.warning("Cannot list directory %s: %s", error.filename, error)

    walker = os.walk(root, onerror=_on_walk_error, followlinks=follow_symlinks)
    for dirpath, dirnames, filenames in walker:
        current_dir = Path(dirpath)

        if not follow_symlinks:
            # Prune symlinked subdirectories in place so os.walk does not
            # descend into them.
            dirnames[:] = [name for name in dirnames if not (current_dir / name).is_symlink()]

        for filename in filenames:
            file_path = current_dir / filename
            if not follow_symlinks and file_path.is_symlink():
                logger.info("Skipping symbolic link: %s", file_path)
                continue
            yield file_path


def build_file_records(
    root: Path,
    chunk_size: int = DEFAULT_HASH_CHUNK_SIZE,
    follow_symlinks: bool = False,
) -> tuple[list[FileRecord], list[FileAccessError]]:
    """Enumerate and hash every file under ``root``.

    Returns ``(records, errors)``. A file that cannot be read (permission
    denied, removed mid-scan, etc.) does not abort the operation -- it is
    logged and returned as a `FileAccessError` instead, and enumeration
    continues with the remaining files (PROJECT_SPEC.md section 7.3/8.3).
    """
    root = Path(root)
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    records: list[FileRecord] = []
    errors: list[FileAccessError] = []

    for file_path in iter_files(root, follow_symlinks=follow_symlinks):
        relative_path = _to_relative_posix(file_path, root)
        try:
            stat_result = file_path.stat()
            sha256 = calculate_sha256(file_path, chunk_size=chunk_size)
        except OSError as exc:
            logger.warning("Could not read file %s: %s", file_path, exc)
            errors.append(FileAccessError(path=relative_path, message=str(exc)))
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
