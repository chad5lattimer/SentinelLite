"""Recursive filesystem enumeration for SentinelLite.

Implements PROJECT_SPEC.md section 8 (filesystem scanning) together with
the hashing step from section 7, producing the ``FileRecord``/
``FileAccessError`` objects consumed by the baseline (Run 3) and scanner
(Run 4) modules.

Symbolic links (section 8.2): SentinelLite does **not** follow symbolic
links by default. Symlinked directories are pruned from traversal and
symlinked files are skipped (and logged), so a link cannot cause infinite
recursion or cause the scan to silently escape the monitored directory.
This is the documented, deliberate behavior for the MVP; callers that
have determined it is safe for their use case may opt in via
``follow_symlinks=True``.

Permission errors (section 8.3) never abort the scan: a directory that
cannot be listed, or a file that cannot be hashed, is logged and recorded
as a ``FileAccessError`` (or simply skipped, for unreadable directories),
and enumeration continues with the remaining files.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from core.hasher import DEFAULT_CHUNK_SIZE, calculate_sha256
from core.models import FileAccessError, FileRecord

logger = logging.getLogger(__name__)


def _to_relative_posix(file_path: Path, root: Path) -> str:
    """Return ``file_path`` relative to ``root`` using forward slashes.

    Relative, forward-slash paths keep baselines portable across machines
    and drive letters (PROJECT_SPEC.md section 6.2).
    """
    return file_path.relative_to(root).as_posix()


def iter_files(root: Path, *, follow_symlinks: bool = False) -> Iterator[Path]:
    """Recursively yield every regular file under ``root``.

    Directories that cannot be listed (permission errors) are logged and
    skipped rather than aborting the walk. See the module docstring for
    the symbolic-link policy.
    """
    root = Path(root)

    def _on_walk_error(error: OSError) -> None:
        logger.warning("Cannot list directory during scan: %s", error)

    for dirpath, dirnames, filenames in os.walk(
        root, onerror=_on_walk_error, followlinks=follow_symlinks
    ):
        dirpath_obj = Path(dirpath)

        if not follow_symlinks:
            # Prune symlinked directories in-place so os.walk does not
            # descend into them.
            dirnames[:] = [
                name for name in dirnames if not (dirpath_obj / name).is_symlink()
            ]

        for filename in filenames:
            file_path = dirpath_obj / filename
            if not follow_symlinks and file_path.is_symlink():
                logger.info("Skipping symbolic link (not followed): %s", file_path)
                continue
            yield file_path


@dataclass
class EnumerationResult:
    """The outcome of enumerating and hashing a directory tree."""

    records: list[FileRecord] = field(default_factory=list)
    errors: list[FileAccessError] = field(default_factory=list)


def build_file_records(
    root: Path,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    follow_symlinks: bool = False,
) -> EnumerationResult:
    """Recursively enumerate and hash every file under ``root``.

    Each readable file becomes a ``FileRecord`` (relative path, SHA-256
    hash, size, modified time). A file that exists but cannot be read
    (permission denied, removed mid-scan, etc.) is recorded as a
    ``FileAccessError`` and does not stop the scan (section 7.3).
    """
    root = Path(root)
    result = EnumerationResult()

    for file_path in iter_files(root, follow_symlinks=follow_symlinks):
        relative_path = _to_relative_posix(file_path, root)
        try:
            stat_result = file_path.stat()
            sha256 = calculate_sha256(file_path, chunk_size=chunk_size)
        except OSError as exc:
            logger.warning("Unable to read file %s: %s", file_path, exc)
            result.errors.append(FileAccessError(path=relative_path, message=str(exc)))
            continue

        result.records.append(
            FileRecord(
                path=relative_path,
                sha256=sha256,
                size=stat_result.st_size,
                modified_time=stat_result.st_mtime,
            )
        )

    return result
