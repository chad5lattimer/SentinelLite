"""Recursive filesystem enumeration for SentinelLite.

Per PROJECT_SPEC.md section 8:
    - The scanner recursively traverses the selected directory.
    - All files are included by default.
    - Directories themselves are not hashed -- only files.
    - Symbolic links are not followed by default (documented in
      `iter_files` below), to avoid infinite recursion and to avoid
      silently pulling in content from outside the monitored tree.
    - Permission errors on individual files or subdirectories must not
      terminate the entire scan.

This module builds `core.models.FileRecord` objects using
`core.hasher.calculate_sha256`; it contains no baseline-comparison logic
(that is `core/scanner.py`, added in a later run).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from core.hasher import calculate_sha256
from core.models import FileRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FileAccessError:
    """A file that could not be read/hashed while collecting file records.

    Per PROJECT_SPEC.md section 7.3, such errors must not crash the
    operation in progress (baseline creation or a scan) -- they are
    collected here so the caller can log them and inform the user once the
    operation completes.
    """

    path: str
    error: str


def iter_files(root_directory: Path, *, follow_symlinks: bool = False) -> Iterator[Path]:
    """Recursively yield every regular file under `root_directory`.

    Directories (and files within them) that cannot be listed due to a
    permission error are skipped and logged rather than raising -- this
    uses `os.walk`'s `onerror` callback so traversal continues into
    sibling directories (PROJECT_SPEC.md section 8.3).

    Symbolic links are not followed by default (PROJECT_SPEC.md section
    8.2): a symlink to a directory is not descended into, and a symlink to
    a file is skipped rather than hashed. This avoids infinite recursion on
    a cyclical link and avoids implicitly expanding the monitored tree to
    include files outside the selected directory. Pass
    `follow_symlinks=True` to opt into following them.

    Filenames within each directory are yielded in sorted order for
    deterministic, reproducible baselines and scan results. Directories are
    visited top-down (a directory's own files are yielded before the files
    of its subdirectories).
    """
    root_directory = Path(root_directory)

    def _on_walk_error(exc: OSError) -> None:
        logger.warning("Could not access directory during scan: %s", exc)

    for dirpath, dirnames, filenames in os.walk(
        root_directory, onerror=_on_walk_error, followlinks=follow_symlinks
    ):
        current_dir = Path(dirpath)

        if not follow_symlinks:
            # Prevent os.walk from descending into symlinked directories.
            dirnames[:] = [
                name for name in dirnames if not (current_dir / name).is_symlink()
            ]

        for filename in sorted(filenames):
            entry = current_dir / filename
            try:
                if entry.is_symlink() and not follow_symlinks:
                    continue
            except OSError as exc:
                logger.warning("Could not stat %s: %s", entry, exc)
                continue
            yield entry


def collect_file_records(
    root_directory: Path,
    *,
    chunk_size: int | None = None,
) -> tuple[list[FileRecord], list[FileAccessError]]:
    """Enumerate `root_directory` and hash every readable file within it.

    Returns a `(records, errors)` tuple: `records` are the successfully
    hashed `FileRecord`s (relative paths, sorted), and `errors` describe
    any files that could not be read, per PROJECT_SPEC.md section 7.3.
    Encountering an unreadable file never stops processing of the
    remaining files.
    """
    root_directory = Path(root_directory)
    hash_kwargs = {} if chunk_size is None else {"chunk_size": chunk_size}

    records: list[FileRecord] = []
    errors: list[FileAccessError] = []

    for file_path in iter_files(root_directory):
        relative_path = file_path.relative_to(root_directory).as_posix()
        try:
            stat_result = file_path.stat()
            sha256 = calculate_sha256(file_path, **hash_kwargs)
        except OSError as exc:
            logger.warning("Could not read %s: %s", file_path, exc)
            errors.append(FileAccessError(path=relative_path, error=str(exc)))
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
