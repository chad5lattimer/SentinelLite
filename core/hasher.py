"""SHA-256 file hashing.

Per PROJECT_SPEC.md section 7:
    - SHA-256 only (no MD5/SHA-1) for integrity comparisons.
    - Files are hashed incrementally, in chunks, so large files never need
      to be loaded into memory whole.

This module performs no filesystem enumeration and no error swallowing:
callers (``core.filesystem``) decide how to handle an unreadable file.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from config import DEFAULT_HASH_CHUNK_SIZE


def calculate_sha256(file_path: Path, chunk_size: int = DEFAULT_HASH_CHUNK_SIZE) -> str:
    """Return the hex-encoded SHA-256 digest of the file at ``file_path``.

    Reads the file incrementally in ``chunk_size``-byte chunks (default
    1 MiB, per PROJECT_SPEC.md section 7.2) rather than loading it into
    memory at once.

    Raises ``OSError`` (e.g. ``PermissionError``, ``FileNotFoundError``)
    if the file cannot be opened or read; raises ``ValueError`` if
    ``chunk_size`` is not positive. Callers that must not abort on an
    unreadable file (e.g. during a directory scan) should catch
    ``OSError`` around this call.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive number of bytes.")

    digest = hashlib.sha256()
    with open(file_path, "rb") as file:
        while chunk := file.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
