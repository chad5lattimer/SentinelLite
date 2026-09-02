"""SHA-256 file hashing utilities.

Per PROJECT_SPEC.md section 7:

- Use SHA-256 exclusively (never MD5/SHA-1) for integrity comparisons.
- Hash incrementally in chunks so large files are never fully loaded into
  memory. The chunk size is configurable, with a 1 MiB default.

This module intentionally does not catch file-read errors: unreadable
files must not be silently treated as "hashed". Callers (see
`core.filesystem`) are responsible for catching `OSError` per file and
recording an ERROR result, so a single unreadable file cannot abort an
entire scan.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from config import DEFAULT_HASH_CHUNK_SIZE


def calculate_sha256(file_path: Path, chunk_size: int = DEFAULT_HASH_CHUNK_SIZE) -> str:
    """Compute the SHA-256 hex digest of `file_path`, reading in chunks.

    Raises:
        ValueError: if `chunk_size` is not a positive integer.
        OSError: if the file cannot be opened or read (e.g. it does not
            exist, was deleted mid-scan, or permission is denied).
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer.")

    sha256 = hashlib.sha256()
    with open(file_path, "rb") as file:
        while chunk := file.read(chunk_size):
            sha256.update(chunk)
    return sha256.hexdigest()
