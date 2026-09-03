"""Recursive filesystem enumeration and hashing.

Implements PROJECT_SPEC.md section 8 (Filesystem Scanning) and the Run 2
acceptance criteria: enumerate a directory, hash every readable file,
produce ``FileRecord`` objects, and continue past inaccessible files
rather than aborting the whole scan.

Design decisions (documented per spec section 8.2):
    - Symbolic links are **not** followed. A symlinked directory is not
      recursed into, and a symlinked file is skipped rather than hashed,
      because the same on-disk link could point at different targets
      between baseline creation and a later scan, or escape the monitored
      root entirely -- neither is a case this MVP tries to reason about.
    - Permission errors and other OS errors (per section 8.3 / 7.3) are
      captured per-file/per-directory as ``FileError`` entries instead of
      raising, so a single inaccessible file or folder never aborts the
      rest of the scan.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable, NamedTuple

from core.hasher import FileHashError, calculate_sha256
from core.models import FileError, FileRecord

logger = logging.getLogger(__name__)

#: Optional callback invoked after each file is processed, as
#: ``(files_done, relative_path)``. Used by the GUI (Run 5) to display
#: scan progress without the core engine depending on any GUI toolkit.
ProgressCallback = Callable[[int, str], None]


class EnumerationResult(NamedTuple):
    """Result of walking a directory tree for candidate files.

    ``paths`` holds absolute paths to regular files that should be
    hashed; ``errors`` holds directories that could not be listed (e.g.
    due to a permission error).
    """

    paths: list[Path]
    errors: list[FileError]


def _relative_posix_path(path: Path, root: Path) -> str:
    """Return ``path`` relative to ``root`` using POSIX-style separators.

    Baselines are stored with forward-slash paths (PROJECT_SPEC.md
    section 6.2) so they remain portable between platforms.
    """
    return path.relative_to(root).as_posix()


def enumerate_files(root: Path) -> EnumerationResult:
    """Recursively enumerate regular files under ``root``.

    Directories are walked top-down without following symbolic links
    (see module docstring). A directory that raises a permission error
    while being listed is recorded as a ``FileError`` and skipped; the
    walk continues with sibling directories.

    Args:
        root: The directory to enumerate. Must exist and be a directory.

    Returns:
        An ``EnumerationResult`` with absolute file paths and any
        directory-level errors encountered.
    """
    root = Path(root)
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    paths: list[Path] = []
    errors: list[FileError] = []

    def _on_walk_error(exc: OSError) -> None:
        rel = _relative_posix_path(Path(exc.filename), root) if exc.filename else "."
        logger.warning("Permission error listing directory %r: %s", exc.filename, exc)
        errors.append(FileError(path=rel, message=str(exc)))

    for dirpath, dirnames, filenames in os.walk(root, onerror=_on_walk_error, followlinks=False):
        current_dir = Path(dirpath)

        # Do not recurse into symlinked directories (documented above).
        dirnames[:] = [
            name for name in dirnames if not (current_dir / name).is_symlink()
        ]

        for filename in filenames:
            file_path = current_dir / filename
            if file_path.is_symlink():
                logger.debug("Skipping symlinked file: %s", file_path)
                continue
            paths.append(file_path)

    return EnumerationResult(paths=paths, errors=errors)


def hash_directory(
    root: Path,
    chunk_size: int | None = None,
    on_progress: ProgressCallback | None = None,
) -> tuple[list[FileRecord], list[FileError]]:
    """Enumerate and hash every readable file under ``root``.

    Args:
        root: Directory to scan.
        chunk_size: Optional override for the hashing chunk size; falls
            back to ``core.hasher``'s default (1 MiB) when omitted.
        on_progress: Optional callback invoked as ``(files_done,
            relative_path)`` after each file is processed (hashed or
            failed), so a caller can display progress without this
            module depending on any GUI toolkit.

    Returns:
        A tuple of ``(records, errors)``:
            - ``records``: ``FileRecord`` objects for every file that
              was successfully hashed.
            - ``errors``: ``FileError`` objects for directories that
              could not be listed and files that could not be hashed
              (e.g. permission denied, removed mid-scan).

    Files are processed in a stable order (as returned by enumeration) so
    results are reproducible across runs against an unchanged directory.
    """
    root = Path(root)
    enumeration = enumerate_files(root)

    records: list[FileRecord] = []
    errors: list[FileError] = list(enumeration.errors)

    hash_kwargs = {} if chunk_size is None else {"chunk_size": chunk_size}

    for index, file_path in enumerate(enumeration.paths, start=1):
        relative_path = _relative_posix_path(file_path, root)
        try:
            digest = calculate_sha256(file_path, **hash_kwargs)
            stat_result = file_path.stat()
        except (FileHashError, OSError) as exc:
            message = str(exc.original_error) if isinstance(exc, FileHashError) else str(exc)
            logger.warning("Could not read file %r: %s", str(file_path), message)
            errors.append(FileError(path=relative_path, message=message))
        else:
            records.append(
                FileRecord(
                    path=relative_path,
                    sha256=digest,
                    size=stat_result.st_size,
                    modified_time=stat_result.st_mtime,
                )
            )

        if on_progress is not None:
            on_progress(index, relative_path)

    return records, errors
