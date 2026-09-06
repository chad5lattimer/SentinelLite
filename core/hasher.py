"""SHA-256 file hashing for SentinelLite.

Per PROJECT_SPEC.md section 7:
    - SHA-256 (via `hashlib`) is the only algorithm used for integrity
      comparisons -- never MD5 or SHA-1.
    - Files are hashed incrementally in chunks so that large files do not
      need to be loaded into memory.

This module contains no filesystem-traversal or GUI logic -- only hashing.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from config import DEFAULT_HASH_CHUNK_SIZE


def calculate_sha256(file_path: Path, chunk_size: int = DEFAULT_HASH_CHUNK_SIZE) -> str:
    """Return the lowercase hex-encoded SHA-256 digest of `file_path`.

    Reads the file incrementally (`chunk_size` bytes at a time, default
    1 MiB) rather than loading it entirely into memory, per
    PROJECT_SPEC.md section 7.2.

    Raises:
        OSError: if the file cannot be opened or read (for example, a
            permission error or the file vanishing mid-read). Callers that
            enumerate many files are expected to catch this per-file and
            continue -- see `core.filesystem.collect_file_records`.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer")

    sha256 = hashlib.sha256()
    with open(file_path, "rb") as file:
        while chunk := file.read(chunk_size):
            sha256.update(chunk)
    return sha256.hexdigest()
