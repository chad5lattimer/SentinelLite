"""Recursive filesystem enumeration for SentinelLite.

Per PROJECT_SPEC.md section 8 (Filesystem Scanning):
    - Recursively traverse the selected directory; all files are included
      by default.
    - Directories themselves are not hashed -- only files.
    - Symbolic links are not followed (see ``Design decision`` below).
    - A permission error (or any other unreadable file) must not terminate
      the scan; it is recorded and enumeration continues.

Design decision -- symbolic links (PROJECT_SPEC.md section 8.2):
    This MVP does not follow symbolic links, for both directories and
    individual files. Following symlinked directories risks infinite
    recursion (a link that points back at an ancestor) and can silently
    pull files from outside the monitored root into the baseline, which
    would be surprising for an integrity-monitoring tool. Symlinked files
    are skipped for the same "stay inside the monitored root" reasoning.
    This is documented rather than "explicitly determined to be safe", so
    per the spec the conservative default (do not follow) applies.

This module only enumerates and hashes files into FileRecord/FileError
objects -- it has no baseline or comparison logic (that lives in
core.baseline and core.scanner).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable, Iterator

from core.hasher import calculate_sha256
from core.models import FileError, FileRecord

logger = logging.getLogger(__name__)

#: Optional callback invoked after each file is processed:
#: (files_processed_so_far, current_relative_path) -> None.
ProgressCallback = Callable[[int, str], None]


def _iter_file_paths(root: Path) -> Iterator[Path]:
    """Yield every regular file under ``root``, recursively.

    Symbolic links (to files or directories) are not followed -- see the
    module-level "Design decision" note above. Directories that cannot be
    listed (permission denied) are skipped with a logged warning rather
    than aborting enumeration.
    """

    def _on_walk_error(error: OSError) -> None:
        logger.warning("Cannot list directory %s: %s", error.filename, error)

    for dirpath, dirnames, filenames in os.walk(root, onerror=_on_walk_error, followlinks=False):
        current_dir = Path(dirpath)

        # Do not descend into symlinked subdirectories.
        dirnames[:] = [d for d in dirnames if not (current_dir / d).is_symlink()]

        for name in filenames:
            file_path = current_dir / name
            if file_path.is_symlink():
                logger.info("Skipping symbolic link (not followed): %s", file_path)
                continue
            yield file_path


def scan_directory(
    root: Path,
    progress_callback: ProgressCallback | None = None,
    chunk_size: int | None = None,
) -> tuple[list[FileRecord], list[FileError]]:
    """Recursively enumerate and hash every file under ``root``.

    Args:
        root: Directory to scan. Must exist and be a directory.
        progress_callback: Optional callback invoked after each file is
            processed, receiving the running count and the file's path
            relative to ``root``. Intended for GUI progress display
            (PROJECT_SPEC.md section 13); this module has no GUI
            dependency itself.
        chunk_size: Optional override for the hashing chunk size, in bytes.
            Defaults to ``core.hasher``'s default (1 MiB) when omitted.

    Returns:
        A tuple ``(records, errors)``:
            - ``records``: a ``FileRecord`` for every file that was
              successfully hashed, with ``path`` relative to ``root``
              using forward slashes.
            - ``errors``: a ``FileError`` for every file that could not be
              read (e.g. permission denied, removed mid-scan), in the same
              relative-path form. These do not stop the scan.

    Raises:
        NotADirectoryError: If ``root`` does not exist or is not a
            directory. This is a caller-configuration error, distinct from
            a per-file read failure, so it is not swallowed into
            ``errors``.
    """
    root = Path(root)
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    records: list[FileRecord] = []
    errors: list[FileError] = []
    processed = 0

    hash_kwargs = {} if chunk_size is None else {"chunk_size": chunk_size}

    for file_path in _iter_file_paths(root):
        relative_path = file_path.relative_to(root).as_posix()
        try:
            stat_result = file_path.stat()
            digest = calculate_sha256(file_path, **hash_kwargs)
        except OSError as error:
            logger.warning("Could not read file %s: %s", file_path, error)
            errors.append(FileError(path=relative_path, message=str(error)))
        else:
            records.append(
                FileRecord(
                    path=relative_path,
                    sha256=digest,
                    size=stat_result.st_size,
                    modified_time=stat_result.st_mtime,
                )
            )

        processed += 1
        if progress_callback is not None:
            progress_callback(processed, relative_path)

    return records, errors
