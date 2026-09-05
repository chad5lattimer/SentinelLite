"""SHA-256 file hashing for SentinelLite.

Implements PROJECT_SPEC.md section 7: hashing must use SHA-256 (never MD5
or SHA-1), and files must be hashed incrementally in chunks rather than
loaded entirely into memory.

This module performs no filesystem enumeration and no error suppression --
if a file cannot be opened or read, the underlying ``OSError`` propagates
to the caller (core.filesystem), which is responsible for recording it as
a ``FileAccessError`` and continuing the scan.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

#: Default chunk size for incremental reads (1 MiB), per section 7.2.
DEFAULT_CHUNK_SIZE: int = 1024 * 1024


def calculate_sha256(file_path: Path, chunk_size: int = DEFAULT_CHUNK_SIZE) -> str:
    """Compute the SHA-256 hex digest of ``file_path``.

    Reads the file in ``chunk_size``-byte chunks so that files far larger
    than available memory can be hashed safely.

    Raises:
        OSError: if the file cannot be opened or read (e.g. permission
            denied, or the file was deleted mid-scan). Callers are
            expected to catch this and record a recoverable error rather
            than let it crash the scan (PROJECT_SPEC.md section 7.3).
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive number of bytes.")

    digest = hashlib.sha256()
    with open(file_path, "rb") as file:
        while chunk := file.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
