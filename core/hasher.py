"""SHA-256 file hashing (PROJECT_SPEC.md section 7).

Only SHA-256 (via the standard-library `hashlib`) is used for integrity
comparisons -- MD5 and SHA-1 are not used anywhere in SentinelLite. Files
are hashed incrementally in fixed-size chunks so that large files never
need to be loaded into memory in full.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from config import DEFAULT_HASH_CHUNK_SIZE


def calculate_sha256(file_path: Path, chunk_size: int = DEFAULT_HASH_CHUNK_SIZE) -> str:
    """Return the lowercase hex SHA-256 digest of the file at ``file_path``.

    The file is read incrementally, ``chunk_size`` bytes at a time
    (default: 1 MiB, per PROJECT_SPEC.md section 7.2), so multi-gigabyte
    files do not need to fit in memory at once.

    Raises:
        ValueError: if ``chunk_size`` is not a positive integer.
        OSError: if the file cannot be opened or read (missing,
            permission denied, disappeared mid-scan, etc.). Per
            PROJECT_SPEC.md section 7.3, callers scanning a directory are
            responsible for catching this and recording a non-fatal
            per-file error rather than letting it abort the scan.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer.")

    digest = hashlib.sha256()
    with open(file_path, "rb") as file:
        while chunk := file.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
