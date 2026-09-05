"""Recursive filesystem enumeration (PROJECT_SPEC.md section 8).

Walks a monitored directory, hashes every readable file, and returns
:class:`~core.models.FileRecord` objects using paths relative to the
monitored root (per section 6.2). Inaccessible files and directories are
skipped without aborting the rest of the scan (section 8.3 / 7.3); each
failure is logged and returned as a :class:`~core.models.FileAccessError`
so the caller can inform the user afterward.

Symbolic link policy (section 8.2): SentinelLite does **not** follow
symbolic links, for either files or directories. Following symlinked
directories risks infinite recursion (a link cycle) and can cause the
same file to be hashed under multiple paths; following symlinked files
would mean the baseline reflects a target the monitored directory does
not actually contain. Symlinks encountered during a scan are skipped and
logged at DEBUG level. This is a conservative default, not a determination
that following links is unsafe in every deployment -- it may be revisited
if a future run has a concrete requirement for it.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterator

from config import DEFAULT_HASH_CHUNK_SIZE
from core.hasher import HashError, calculate_sha256
from core.models import FileAccessError, FileRecord

logger = logging.getLogger(__name__)


def iter_files(root: Path) -> Iterator[Path]:
    """Recursively yield every regular file under ``root``.

    Symbolic links (to files or directories) are not followed -- see the
    module docstring. Directories that cannot be listed (e.g. permission
    denied) are skipped and logged rather than raising.
    """

    def _on_walk_error(exc: OSError) -> None:
        logger.warning("Unable to list directory: %s (%s)", exc.filename, exc)

    for dirpath, dirnames, filenames in os.walk(root, onerror=_on_walk_error, followlinks=False):
        current_dir = Path(dirpath)

        # os.walk() with followlinks=False already avoids *descending* into
        # symlinked directories, but it still lists them in dirnames; drop
        # them explicitly for clarity and so callers relying on iter_files
        # alone see consistent behavior.
        dirnames[:] = [name for name in dirnames if not (current_dir / name).is_symlink()]

        for filename in filenames:
            file_path = current_dir / filename
            if file_path.is_symlink():
                logger.debug("Skipping symbolic link (not followed): %s", file_path)
                continue
            yield file_path


def build_file_records(
    root: Path,
    chunk_size: int = DEFAULT_HASH_CHUNK_SIZE,
) -> tuple[list[FileRecord], list[FileAccessError]]:
    """Enumerate and hash every file under ``root``.

    Returns a ``(records, errors)`` tuple. A file that cannot be read
    (permission error, disappears mid-scan, etc.) is recorded in
    ``errors`` and does not prevent the remaining files from being
    processed, per PROJECT_SPEC.md sections 7.3 and 8.3.
    """
    root = Path(root)
    records: list[FileRecord] = []
    errors: list[FileAccessError] = []

    for file_path in iter_files(root):
        relative_path = file_path.relative_to(root).as_posix()
        try:
            stat_result = file_path.stat()
            sha256 = calculate_sha256(file_path, chunk_size=chunk_size)
        except (OSError, HashError) as exc:
            logger.warning("Skipping unreadable file: %s (%s)", file_path, exc)
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
