"""SHA-256 file hashing for SentinelLite.

Per PROJECT_SPEC.md section 7:
    - SHA-256 only (no MD5/SHA-1) for integrity comparisons.
    - Files are hashed incrementally in chunks so large files never need
      to be loaded into memory at once.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from config import DEFAULT_HASH_CHUNK_SIZE


def calculate_sha256(file_path: Path, chunk_size: int = DEFAULT_HASH_CHUNK_SIZE) -> str:
    """Return the lowercase hex SHA-256 digest of ``file_path``.

    Reads the file incrementally (``chunk_size`` bytes at a time, default
    1 MiB) rather than loading it into memory in one go.

    Raises ``OSError`` (including subclasses such as ``PermissionError``
    and ``FileNotFoundError``) if the file cannot be read. Callers that
    need to continue processing other files after a failure -- as required
    by PROJECT_SPEC.md section 7.3 -- should catch ``OSError`` around this
    call; this function itself does not swallow errors.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer")

    digest = hashlib.sha256()
    with open(file_path, "rb") as file:
        while chunk := file.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
