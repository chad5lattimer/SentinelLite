"""SHA-256 file hashing for SentinelLite.

Per PROJECT_SPEC.md section 7:
    - SHA-256 (via `hashlib`) is the only algorithm used for integrity
      comparisons -- MD5/SHA-1 are not used.
    - Files are hashed incrementally, in chunks, so large files do not need
      to be loaded into memory.

This module contains no filesystem traversal or GUI logic; it only knows
how to hash a single file given its path.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from config import DEFAULT_HASH_CHUNK_SIZE


def calculate_sha256(file_path: Path, chunk_size: int = DEFAULT_HASH_CHUNK_SIZE) -> str:
    """Compute the hex-encoded SHA-256 digest of a file's contents.

    Reads the file incrementally in ``chunk_size``-byte chunks (default
    1 MiB, per PROJECT_SPEC.md section 7.2) rather than loading the entire
    file into memory, so large files can be hashed with bounded memory use.

    Args:
        file_path: Path to the file to hash.
        chunk_size: Number of bytes to read per chunk. Must be positive.

    Returns:
        The lowercase hex-encoded SHA-256 digest.

    Raises:
        ValueError: If ``chunk_size`` is not positive.
        OSError: If the file cannot be opened or read (e.g. it does not
            exist, permission is denied, or it disappears mid-read). Per
            PROJECT_SPEC.md section 7.3, callers are responsible for
            catching this, logging it, recording an ERROR result, and
            continuing the scan rather than letting it propagate and abort
            the run.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive number of bytes.")

    digest = hashlib.sha256()
    with open(file_path, "rb") as file:
        while chunk := file.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
