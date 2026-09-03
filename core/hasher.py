"""SHA-256 file hashing for SentinelLite.

Implements PROJECT_SPEC.md section 7 (Hashing Requirements): SHA-256 via
the standard-library ``hashlib``, incremental/chunked reads so large files
are never fully loaded into memory, and a configurable chunk size.

This module contains no filesystem enumeration or GUI logic -- callers
(core/filesystem.py) decide which files to hash and how to handle
failures.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from config import DEFAULT_HASH_CHUNK_SIZE

#: SHA-256 of the empty byte string, i.e. the hash of an empty file.
EMPTY_FILE_SHA256 = hashlib.sha256(b"").hexdigest()


def calculate_sha256(file_path: Path, chunk_size: int = DEFAULT_HASH_CHUNK_SIZE) -> str:
    """Return the lowercase hex SHA-256 digest of ``file_path``.

    Reads the file incrementally in ``chunk_size``-byte chunks (default
    1 MiB, per PROJECT_SPEC.md section 7.2) so memory usage stays constant
    regardless of file size, including for empty files.

    Raises ``OSError`` (e.g. ``PermissionError``, ``FileNotFoundError``) if
    the file cannot be opened or read. Callers are responsible for
    catching this and recording it as a non-fatal error (section 7.3) --
    this function does not swallow errors itself.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer.")

    digest = hashlib.sha256()
    with open(file_path, "rb") as file:
        while chunk := file.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
