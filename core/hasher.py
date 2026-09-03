"""SHA-256 file hashing for SentinelLite.

Per PROJECT_SPEC.md section 7:
    - SHA-256 only (no MD5/SHA-1) for integrity comparisons.
    - Files are hashed incrementally, in chunks, so large files never need
      to be loaded into memory in full.
    - Errors reading a file are not swallowed here: callers (the
      filesystem engine, and later the scanner) are responsible for
      catching them, recording an ERROR result, and continuing.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from config import DEFAULT_HASH_CHUNK_SIZE


def calculate_sha256(file_path: Path, chunk_size: int = DEFAULT_HASH_CHUNK_SIZE) -> str:
    """Compute the SHA-256 hash of a file's contents as a lowercase hex string.

    Reads the file incrementally in ``chunk_size``-byte chunks (default
    1 MiB, per PROJECT_SPEC.md section 7.2) rather than loading it entirely
    into memory, so this scales to large files.

    Raises ``OSError`` (e.g. ``FileNotFoundError``, ``PermissionError``) if
    the file cannot be opened or read. Callers should catch this rather
    than letting it propagate into a scan loop, per section 7.3.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer")

    digest = hashlib.sha256()
    with open(file_path, "rb") as file_obj:
        while chunk := file_obj.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
