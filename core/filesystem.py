"""Recursive filesystem enumeration and hashing.

Combines directory traversal (this module) with SHA-256 hashing
(``core.hasher``) to turn a monitored directory into a list of
``FileRecord`` objects, per PROJECT_SPEC.md sections 7-8.

This module contains no GUI code and no baseline/comparison logic -- it
only knows how to read the filesystem.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable, Iterator, NamedTuple

from config import DEFAULT_HASH_CHUNK_SIZE
from core.hasher import calculate_sha256
from core.models import FileAccessError, FileRecord

logger = logging.getLogger(__name__)

#: Optional callback invoked after each file is processed, receiving the
#: number of files processed so far and the path most recently processed.
#: Used by the GUI (Run 5) to drive a progress bar; the engine itself has
#: no notion of "the GUI" and does not require a callback to function.
ProgressCallback = Callable[[int, str], None]


class ScanOutcome(NamedTuple):
    """The result of enumerating and hashing a directory tree."""

    records: list[FileRecord]
    errors: list[FileAccessError]


def iter_files(root: Path, follow_symlinks: bool = False) -> Iterator[Path]:
    """Recursively yield every regular file under ``root``.

    Directories are not yielded (PROJECT_SPEC.md section 8.1: only files
    need to be recorded).

    Symbolic links are not followed by default (PROJECT_SPEC.md section
    8.2: "avoid recursively following symbolic links unless explicitly
    determined to be safe"). This avoids infinite loops from cyclic links
    and prevents a monitored directory from silently pulling in content
    from outside itself. A symlink to a file is skipped rather than
    hashed, since the link's target is not really "inside" the monitored
    directory and its target may itself move independently of the link.
    Passing ``follow_symlinks=True`` opts into following them, for callers
    that have determined it is safe to do so.

    Permission errors encountered while listing a directory are logged and
    that directory is skipped; enumeration of the rest of the tree
    continues (PROJECT_SPEC.md section 8.3).
    """
    for dirpath, dirnames, filenames in os.walk(root, onerror=_log_walk_error, followlinks=follow_symlinks):
        current_dir = Path(dirpath)

        if not follow_symlinks:
            # os.walk() with followlinks=False still yields the *names* of
            # symlinked subdirectories in dirnames (it just doesn't descend
            # into them); nothing further to do for those. Symlinked files
            # are filtered out below.
            pass

        for filename in filenames:
            file_path = current_dir / filename
            if not follow_symlinks and file_path.is_symlink():
                logger.debug("Skipping symbolic link: %s", file_path)
                continue
            yield file_path


def _log_walk_error(error: OSError) -> None:
    logger.warning("Could not list directory during scan: %s", error)


def build_file_record(root: Path, file_path: Path, chunk_size: int = DEFAULT_HASH_CHUNK_SIZE) -> FileRecord:
    """Hash a single file and return its ``FileRecord``, relative to ``root``.

    Raises ``OSError`` (e.g. ``PermissionError``, ``FileNotFoundError``) if
    the file cannot be read or its metadata cannot be retrieved; callers
    that process many files should catch this per file (see
    ``collect_file_records``) rather than letting a single bad file abort
    an entire scan.
    """
    stat_result = file_path.stat()
    digest = calculate_sha256(file_path, chunk_size=chunk_size)
    relative_path = file_path.relative_to(root).as_posix()
    return FileRecord(
        path=relative_path,
        sha256=digest,
        size=stat_result.st_size,
        modified_time=stat_result.st_mtime,
    )


def collect_file_records(
    root: Path,
    chunk_size: int = DEFAULT_HASH_CHUNK_SIZE,
    follow_symlinks: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> ScanOutcome:
    """Enumerate and hash every file under ``root``.

    Returns a ``ScanOutcome`` containing the successfully hashed
    ``FileRecord`` entries and a separate list of ``FileAccessError``
    entries for files that could not be read. A file that cannot be
    accessed never aborts the overall operation (PROJECT_SPEC.md section
    7.3 / 8.3) -- it is recorded as an error and enumeration continues.
    """
    root = Path(root)
    records: list[FileRecord] = []
    errors: list[FileAccessError] = []

    processed = 0
    for file_path in iter_files(root, follow_symlinks=follow_symlinks):
        relative_display = _safe_relative_display(root, file_path)
        try:
            records.append(build_file_record(root, file_path, chunk_size=chunk_size))
        except OSError as exc:
            logger.warning("Could not read file during scan: %s (%s)", file_path, exc)
            errors.append(FileAccessError(path=relative_display, message=str(exc)))

        processed += 1
        if progress_callback is not None:
            progress_callback(processed, relative_display)

    return ScanOutcome(records=records, errors=errors)


def _safe_relative_display(root: Path, file_path: Path) -> str:
    """Best-effort relative-path string for logging/errors/UI display.

    Falls back to the absolute path if ``file_path`` is not (for some
    unexpected reason) inside ``root``, so error reporting never raises.
    """
    try:
        return file_path.relative_to(root).as_posix()
    except ValueError:
        return str(file_path)
