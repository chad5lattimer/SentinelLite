"""Recursive filesystem enumeration and FileRecord collection.

Implements PROJECT_SPEC.md section 8 (Filesystem Scanning): recursive
traversal of a monitored directory, hashing every readable file into a
``FileRecord``. Permission errors and other per-file read failures never
abort the scan (sections 7.3 and 8.3); they are collected as
``FileReadError`` entries so the caller can inform the user once scanning
completes.

Symbolic links (section 8.2): by default this module does not follow
symlinked directories (avoids cycles and escaping the monitored root) and
does not hash symlinked files (avoids silently hashing a target outside
the monitored directory under the entry's name). This is a deliberate,
conservative default; pass ``follow_symlinks=True`` to opt in once that
has been explicitly judged safe for a given use case.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, Optional

from core.hasher import calculate_sha256
from core.models import FileRecord
from config import DEFAULT_HASH_CHUNK_SIZE

logger = logging.getLogger(__name__)

#: Called as (processed_count, total_count, relative_path) after each file.
ProgressCallback = Callable[[int, int, str], None]


@dataclass(frozen=True)
class FileReadError:
    """Records that a file could not be enumerated or hashed."""

    path: str
    message: str


@dataclass(frozen=True)
class EnumerationResult:
    """The outcome of enumerating and hashing a directory tree."""

    records: list[FileRecord]
    errors: list[FileReadError]


def iter_files(root: Path, *, follow_symlinks: bool = False) -> Iterator[Path]:
    """Yield every regular file under ``root``, recursively.

    Directories that cannot be listed (permission errors) are skipped: the
    error is logged and enumeration continues with the rest of the tree
    (PROJECT_SPEC.md section 8.3). See the module docstring for the
    symlink policy (section 8.2).
    """

    def _on_error(error: OSError) -> None:
        logger.warning("Could not list directory: %s (%s)", error.filename, error)

    for dirpath, _dirnames, filenames in os.walk(
        root, onerror=_on_error, followlinks=follow_symlinks
    ):
        dir_path = Path(dirpath)
        for filename in filenames:
            file_path = dir_path / filename
            if not follow_symlinks and file_path.is_symlink():
                continue
            yield file_path


def build_file_records(
    root: Path,
    *,
    chunk_size: int = DEFAULT_HASH_CHUNK_SIZE,
    follow_symlinks: bool = False,
    on_progress: Optional[ProgressCallback] = None,
) -> EnumerationResult:
    """Recursively enumerate ``root`` and hash every readable file.

    Returns an ``EnumerationResult`` pairing a ``FileRecord`` for each file
    that was read successfully with a ``FileReadError`` for each file that
    could not be (PROJECT_SPEC.md section 7.3: the scan continues rather
    than aborting, and each failure is logged here).

    ``on_progress``, if given, is invoked after every file (successful or
    not) with the number processed so far, the total file count, and the
    file's path relative to ``root`` -- intended for a GUI progress display
    (PROJECT_SPEC.md section 13), wired up in Run 5.
    """
    root = Path(root)
    file_paths = list(iter_files(root, follow_symlinks=follow_symlinks))
    total = len(file_paths)

    records: list[FileRecord] = []
    errors: list[FileReadError] = []

    for index, file_path in enumerate(file_paths, start=1):
        relative_path = file_path.relative_to(root).as_posix()
        try:
            stat_result = file_path.stat()
            sha256 = calculate_sha256(file_path, chunk_size=chunk_size)
        except OSError as error:
            logger.warning("Could not read file %s: %s", file_path, error)
            errors.append(FileReadError(path=relative_path, message=str(error)))
        else:
            records.append(
                FileRecord(
                    path=relative_path,
                    sha256=sha256,
                    size=stat_result.st_size,
                    modified_time=stat_result.st_mtime,
                )
            )

        if on_progress is not None:
            on_progress(index, total, relative_path)

    return EnumerationResult(records=records, errors=errors)
