"""Recursive filesystem enumeration and hashing for SentinelLite.

Implements PROJECT_SPEC.md section 8 (filesystem scanning) and the file
side of section 7 (hashing): recursively walk a monitored directory,
hash every readable file with ``core.hasher``, and produce
``FileRecord``/``FileError`` objects (PROJECT_SPEC.md section 6.1).

Symbolic links (PROJECT_SPEC.md section 8.2)
---------------------------------------------
SentinelLite does not follow symbolic links, for both directories and
files. This is a deliberate, documented choice:

    - Symlinked *directories* are not traversed, so a link cannot cause
      unbounded recursion (e.g. a symlink loop) or cause the scan to
      silently leave the monitored root and hash unrelated parts of the
      filesystem.
    - Symlinked *files* are skipped entirely (not hashed) for the same
      reason -- a symlink's target is not guaranteed to remain inside
      the monitored directory, and hashing through it would make the
      baseline depend on filesystem state outside what the user
      selected to monitor.

This matches PROJECT_SPEC.md section 8.2's instruction to avoid
recursively following symbolic links "unless explicitly determined to
be safe" -- symlink-following is not required by the MVP, so the safer
default is used.

Permission errors (PROJECT_SPEC.md section 8.3)
-------------------------------------------------
A directory or file that cannot be accessed must not terminate the
scan. Unreadable directories are skipped (logged) during enumeration;
unreadable files are still yielded so the caller can record an
``ERROR`` result for them rather than silently omitting them.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterator, NamedTuple

from config import DEFAULT_HASH_CHUNK_SIZE
from core.hasher import HashError, calculate_sha256
from core.models import FileError, FileRecord

logger = logging.getLogger(__name__)


class ScanOutcome(NamedTuple):
    """Result of scanning a directory: successfully hashed files, plus
    any files that could not be read."""

    records: list[FileRecord]
    errors: list[FileError]


def _relative_posix_path(root: Path, path: Path) -> str:
    """Return ``path`` relative to ``root`` using forward slashes,
    regardless of the host platform (PROJECT_SPEC.md section 6.2 uses
    forward-slash relative paths in its examples)."""
    return path.relative_to(root).as_posix()


def iter_files(root: Path) -> Iterator[Path]:
    """Recursively yield every regular file under ``root``.

    Directories and files reached only through a symbolic link are not
    yielded (see module docstring). Directories that cannot be listed
    due to a permission error are skipped and logged rather than
    aborting the walk.
    """
    root = Path(root)

    def _on_walk_error(error: OSError) -> None:
        logger.warning("Skipping inaccessible directory during scan: %s", error)

    for current_dir, dir_names, file_names in os.walk(root, onerror=_on_walk_error, followlinks=False):
        current_path = Path(current_dir)

        # Do not descend into symlinked subdirectories (os.walk still lists
        # them in dir_names even with followlinks=False; pruning here keeps
        # the walk from reporting anything inside them).
        dir_names[:] = [
            name for name in dir_names if not (current_path / name).is_symlink()
        ]

        for file_name in file_names:
            file_path = current_path / file_name
            if file_path.is_symlink():
                continue
            yield file_path


def build_file_record(
    root: Path,
    file_path: Path,
    chunk_size: int = DEFAULT_HASH_CHUNK_SIZE,
) -> FileRecord:
    """Hash a single file and return its ``FileRecord``.

    ``file_path`` must be a path to an existing file inside ``root``.

    Raises:
        HashError: if the file's contents cannot be read.
        OSError: if the file's metadata (``stat``) cannot be read.
    """
    stat_result = file_path.stat()
    sha256 = calculate_sha256(file_path, chunk_size=chunk_size)
    return FileRecord(
        path=_relative_posix_path(Path(root), file_path),
        sha256=sha256,
        size=stat_result.st_size,
        modified_time=stat_result.st_mtime,
    )


def scan_directory(root: Path, chunk_size: int = DEFAULT_HASH_CHUNK_SIZE) -> ScanOutcome:
    """Recursively enumerate and hash every readable file under ``root``.

    Files that cannot be read (permission denied, removed mid-scan,
    etc.) do not stop the scan; they are collected as ``FileError``
    entries instead, per PROJECT_SPEC.md sections 7.3 and 8.3.

    Returns:
        A ``ScanOutcome`` with ``records`` (successfully hashed files)
        and ``errors`` (files that could not be read).
    """
    root = Path(root)
    records: list[FileRecord] = []
    errors: list[FileError] = []

    for file_path in iter_files(root):
        relative_path = _relative_posix_path(root, file_path)
        try:
            records.append(build_file_record(root, file_path, chunk_size=chunk_size))
        except (HashError, OSError) as exc:
            message = str(exc)
            logger.warning("Unable to read file during scan: %s (%s)", file_path, message)
            errors.append(FileError(path=relative_path, message=message))

    return ScanOutcome(records=records, errors=errors)
