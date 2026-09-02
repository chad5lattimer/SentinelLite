"""SHA-256 file hashing utilities.

Implements PROJECT_SPEC.md section 7: files are hashed with SHA-256
(section 7.1) read incrementally in fixed-size chunks so that large
files are never loaded fully into memory (section 7.2).

This module knows how to hash a single file and nothing else -- it has
no knowledge of directories, baselines, or scans. Error handling for
"many files, some unreadable" belongs to ``core.filesystem``
(PROJECT_SPEC.md section 7.3).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from config import DEFAULT_HASH_CHUNK_SIZE

__all__ = ["calculate_sha256"]


def calculate_sha256(file_path: Path, chunk_size: int = DEFAULT_HASH_CHUNK_SIZE) -> str:
    """Return the hex-encoded SHA-256 digest of ``file_path``.

    The file is read in ``chunk_size``-byte chunks (default 1 MiB, per
    PROJECT_SPEC.md section 7.2), so memory usage does not scale with
    file size.

    Raises ``OSError`` (e.g. ``PermissionError``, ``FileNotFoundError``,
    ``IsADirectoryError``) if the file cannot be opened or read.
    Callers that hash many files on behalf of a user -- see
    ``core.filesystem.build_file_records`` -- are expected to catch this
    per file and record an ERROR result rather than let one bad file
    abort the whole operation (PROJECT_SPEC.md section 7.3).
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer")

    digest = hashlib.sha256()
    with open(file_path, "rb") as file:
        while chunk := file.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
