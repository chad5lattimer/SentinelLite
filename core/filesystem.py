"""Recursive filesystem enumeration and FileRecord collection.

Per PROJECT_SPEC.md section 8 (Filesystem Scanning) and section 27
(Run 2 objectives): recursively traverse a monitored directory, include
all files by default, collect metadata alongside each file's SHA-256
hash, and never let a permission error -- or any other per-file/per-
directory OSError -- abort the whole scan.

Symbolic links (section 8.2): SentinelLite does not follow symbolic
links. A symlinked file is skipped, and `os.walk` is run with
`followlinks=False` so a symlinked directory is never descended into.
This is the documented, chosen behavior -- it avoids both symlink
cycles and a baseline silently reaching outside the monitored directory
through a link.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional

from core.hasher import calculate_sha256
from core.models import FileRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FileScanError:
    """A single file that could not be enumerated, stat'd, or hashed."""

    path: str
    message: str


@dataclass(frozen=True)
class ScanOutcome:
    """The result of walking and hashing a directory tree."""

    records: List[FileRecord]
    errors: List[FileScanError]


def iter_file_paths(root: Path) -> Iterator[Path]:
    """Yield every regular file under `root`, walked recursively.

    Directory-level permission errors (a subdirectory that cannot be
    listed) are logged and skipped rather than raised, so one
    inaccessible subtree does not abort enumeration of the rest of the
    tree (PROJECT_SPEC.md section 8.3).
    """

    def _on_walk_error(error: OSError) -> None:
        logger.warning("Could not list directory %s: %s", error.filename, error)

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False, onerror=_on_walk_error):
        current_dir = Path(dirpath)
        # Belt-and-braces: os.walk(followlinks=False) already avoids
        # descending into symlinked directories, but filtering dirnames
        # in place keeps that guarantee explicit and self-documenting.
        dirnames[:] = [name for name in dirnames if not (current_dir / name).is_symlink()]
        for filename in filenames:
            file_path = current_dir / filename
            if file_path.is_symlink():
                continue
            yield file_path


def build_file_record(root: Path, file_path: Path, chunk_size: Optional[int] = None) -> FileRecord:
    """Hash a single file and build its FileRecord.

    `path` on the resulting record is relative to `root`. Raises OSError
    (e.g. `PermissionError`, `FileNotFoundError`) if the file cannot be
    stat'd or read; callers are expected to catch this per file (see
    `scan_directory`) rather than let it abort enumeration.
    """
    stat_result = file_path.stat()
    sha256 = calculate_sha256(file_path) if chunk_size is None else calculate_sha256(file_path, chunk_size)
    relative_path = file_path.relative_to(root).as_posix()
    return FileRecord(
        path=relative_path,
        sha256=sha256,
        size=stat_result.st_size,
        modified_time=stat_result.st_mtime,
    )


def scan_directory(root: Path, chunk_size: Optional[int] = None) -> ScanOutcome:
    """Recursively enumerate and hash every file under `root`.

    Per PROJECT_SPEC.md section 8.3 / 7.3, a file that cannot be read
    does not abort the scan: it is logged and recorded as a
    `FileScanError`, and enumeration continues with the remaining files.
    """
    root = Path(root)
    records: List[FileRecord] = []
    errors: List[FileScanError] = []

    for file_path in iter_file_paths(root):
        try:
            records.append(build_file_record(root, file_path, chunk_size))
        except OSError as exc:
            relative_path = _safe_relative_path(root, file_path)
            logger.warning("Could not read file %s: %s", file_path, exc)
            errors.append(FileScanError(path=relative_path, message=str(exc)))

    return ScanOutcome(records=records, errors=errors)


def _safe_relative_path(root: Path, file_path: Path) -> str:
    try:
        return file_path.relative_to(root).as_posix()
    except ValueError:
        return str(file_path)
