"""SHA-256 file hashing for SentinelLite.

Per PROJECT_SPEC.md section 7:
    - SHA-256 (via `hashlib`) is the only algorithm used for integrity
      comparisons; MD5/SHA-1 are not used.
    - Files are hashed incrementally, in fixed-size chunks, so that large
      files never need to be fully loaded into memory.

This module contains no filesystem traversal or comparison logic -- see
`core/filesystem.py` and (in a later run) `core/scanner.py`.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from config import DEFAULT_HASH_CHUNK_SIZE


def calculate_sha256(file_path: Path, chunk_size: int = DEFAULT_HASH_CHUNK_SIZE) -> str:
    """Return the hex-encoded SHA-256 digest of the file at `file_path`.

    The file is read incrementally in `chunk_size`-byte chunks (default
    1 MiB, per PROJECT_SPEC.md section 7.2) rather than being loaded into
    memory all at once, so hashing memory usage stays roughly constant
    regardless of file size.

    Raises:
        OSError: If the file cannot be opened or read (e.g. missing file,
            permission denied). Callers that must continue processing other
            files after such an error (per PROJECT_SPEC.md section 7.3)
            should catch `OSError` around this call -- see
            `core/filesystem.collect_file_records`.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive number of bytes.")

    digest = hashlib.sha256()
    with open(file_path, "rb") as file:
        while chunk := file.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
