"""SHA-256 file hashing (PROJECT_SPEC.md section 7).

Hashing is performed incrementally in fixed-size chunks so that large files
never need to be loaded into memory in full. MD5/SHA-1 must not be used for
integrity comparisons -- SHA-256 via the standard-library ``hashlib`` is the
only algorithm used anywhere in SentinelLite.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from config import DEFAULT_HASH_CHUNK_SIZE


def calculate_sha256(
    file_path: Path,
    chunk_size: int = DEFAULT_HASH_CHUNK_SIZE,
) -> str:
    """Return the lowercase hex-encoded SHA-256 digest of ``file_path``.

    Reads the file incrementally (``chunk_size`` bytes at a time) rather
    than loading it into memory in full, per PROJECT_SPEC.md section 7.2.

    Raises ``OSError`` (e.g. ``PermissionError``, ``FileNotFoundError``) if
    the file cannot be opened or read. Callers are responsible for catching
    this and recording it as a ``FileAccessError`` instead of letting it
    abort a scan (PROJECT_SPEC.md section 7.3) -- this function does not
    swallow errors itself.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive number of bytes.")

    sha256 = hashlib.sha256()
    with open(file_path, "rb") as file:
        while chunk := file.read(chunk_size):
            sha256.update(chunk)
    return sha256.hexdigest()
