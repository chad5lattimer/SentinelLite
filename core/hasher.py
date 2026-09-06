"""SHA-256 file hashing for SentinelLite.

Per PROJECT_SPEC.md section 7:
    - SHA-256 only (no MD5/SHA-1) for integrity comparisons.
    - Files are hashed incrementally in chunks so large files never need to
      be loaded into memory in full.
    - A file that cannot be read must not crash the caller; it is the
      caller's responsibility (see core.filesystem) to catch the resulting
      OSError, record an ERROR, log it, and continue.

This module contains only hashing logic -- no directory traversal, no
GUI code.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from config import DEFAULT_HASH_CHUNK_SIZE


def calculate_sha256(file_path: Path, chunk_size: int = DEFAULT_HASH_CHUNK_SIZE) -> str:
    """Compute the SHA-256 hex digest of a file's contents.

    Reads the file incrementally in ``chunk_size``-byte chunks (default
    1 MiB, per PROJECT_SPEC.md section 7.2) so memory usage stays constant
    regardless of file size.

    Args:
        file_path: Path to the file to hash.
        chunk_size: Number of bytes to read per chunk. Must be positive.

    Returns:
        The lowercase hex-encoded SHA-256 digest.

    Raises:
        OSError: If the file cannot be opened or read (e.g. permission
            denied, file removed mid-scan). Callers that hash many files
            (see core.filesystem) are expected to catch this per-file so a
            single unreadable file does not abort the whole scan.
        ValueError: If ``chunk_size`` is not positive.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive number of bytes.")

    digest = hashlib.sha256()
    with open(file_path, "rb") as file:
        while chunk := file.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
