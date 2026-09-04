"""SHA-256 file hashing.

Per PROJECT_SPEC.md section 7:
    - SHA-256 only (no MD5/SHA-1) for integrity comparisons.
    - Files are hashed incrementally, in chunks, so large files never need
      to be loaded into memory in full.
    - Read/permission errors are the caller's responsibility to handle
      (see core.filesystem), so this module simply lets them propagate as
      standard OSError subclasses rather than swallowing them.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from config import DEFAULT_HASH_CHUNK_SIZE


def calculate_sha256(file_path: Path, chunk_size: int = DEFAULT_HASH_CHUNK_SIZE) -> str:
    """Return the lowercase hex-encoded SHA-256 digest of ``file_path``.

    The file is read incrementally in ``chunk_size``-byte chunks (default
    1 MiB, per PROJECT_SPEC.md section 7.2) so memory use stays constant
    regardless of file size.

    Raises whatever ``OSError`` subclass the underlying ``open()``/``read()``
    calls raise (e.g. ``PermissionError``, ``FileNotFoundError``) -- callers
    that scan many files (core.filesystem) are expected to catch these per
    file and continue, per PROJECT_SPEC.md section 7.3.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive number of bytes.")

    digest = hashlib.sha256()
    with open(file_path, "rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
