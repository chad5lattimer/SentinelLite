"""SHA-256 file hashing.

Per PROJECT_SPEC.md section 7:
    - SHA-256 only (never MD5/SHA-1) for integrity comparisons.
    - Files are hashed incrementally in chunks, never loaded fully into
      memory, so large files do not cause excessive memory usage.

This module contains no filesystem traversal or error-recovery policy --
it simply hashes a single, already-resolved file path, and lets I/O
errors (``OSError`` and subclasses, e.g. ``PermissionError`` /
``FileNotFoundError``) propagate to the caller (`core/filesystem.py`),
which is responsible for turning them into `FileAccessError` entries and
continuing the scan.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from config import DEFAULT_HASH_CHUNK_SIZE


def calculate_sha256(file_path: Path, chunk_size: int = DEFAULT_HASH_CHUNK_SIZE) -> str:
    """Return the lowercase hex SHA-256 digest of ``file_path``.

    Reads the file incrementally, ``chunk_size`` bytes at a time (default
    1 MiB, per PROJECT_SPEC.md section 7.2), so memory usage stays
    constant regardless of file size.

    Raises whatever `OSError` subclass the underlying `open()`/`read()`
    calls raise (e.g. `FileNotFoundError`, `PermissionError`) -- callers
    that need to keep scanning past unreadable files should catch
    `OSError` around this call.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive number of bytes")

    digest = hashlib.sha256()
    with open(file_path, "rb") as file:
        while chunk := file.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
