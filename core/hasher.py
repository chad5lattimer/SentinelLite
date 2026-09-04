"""SHA-256 file hashing (PROJECT_SPEC.md section 7).

This module has exactly one job: turn a file on disk into a SHA-256 hex
digest, reading it incrementally so large files do not need to be loaded
into memory. It intentionally does not catch filesystem errors -- callers
(e.g. `core.filesystem`) decide how to handle an unreadable file, per the
error-handling requirements in section 7.3.

MD5/SHA-1 must never be used for integrity comparisons (section 7.1).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from config import DEFAULT_HASH_CHUNK_SIZE

#: The only algorithm approved for integrity hashing in this application.
HASH_ALGORITHM: str = "sha256"


def calculate_sha256(file_path: Path, chunk_size: int = DEFAULT_HASH_CHUNK_SIZE) -> str:
    """Return the SHA-256 hex digest of ``file_path``.

    Reads the file in ``chunk_size``-byte chunks (default 1 MiB) rather
    than loading it into memory at once, per PROJECT_SPEC.md section 7.2.

    Raises:
        OSError: if the file cannot be opened or read (e.g. it does not
            exist, was deleted mid-scan, or permission is denied). Callers
            are responsible for catching this and recording an ERROR
            result instead of letting it crash the scan (section 7.3).
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer")

    digest = hashlib.sha256()
    with open(file_path, "rb") as file:
        while chunk := file.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
