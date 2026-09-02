"""SHA-256 file hashing for SentinelLite.

Per PROJECT_SPEC.md section 7:
    - SHA-256 only (no MD5/SHA-1) for integrity comparisons.
    - Files are hashed incrementally in chunks, never loaded fully into
      memory, so large files do not cause excessive memory usage.
    - A file that cannot be read must not crash the caller -- it raises
      ``HashError`` so the caller (``core.filesystem``, and later
      ``core.scanner``) can record an ERROR result and continue.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from config import DEFAULT_HASH_CHUNK_SIZE


class HashError(Exception):
    """Raised when a file cannot be read/hashed (missing, permission
    denied, or another OS-level error)."""


def calculate_sha256(file_path: Path, chunk_size: int = DEFAULT_HASH_CHUNK_SIZE) -> str:
    """Return the hex-encoded SHA-256 digest of ``file_path``.

    Reads the file incrementally in ``chunk_size``-byte chunks (default
    1 MiB, per PROJECT_SPEC.md section 7.2) so memory usage stays
    constant regardless of file size.

    Raises:
        HashError: if the file cannot be opened or read (e.g. it does
            not exist, a permission error occurs, or another OS-level
            error occurs while reading). The original exception is
            chained via ``__cause__`` for diagnostic/logging purposes.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer.")

    digest = hashlib.sha256()
    try:
        with open(file_path, "rb") as file:
            while chunk := file.read(chunk_size):
                digest.update(chunk)
    except OSError as exc:
        raise HashError(f"Unable to read file: {file_path}") from exc

    return digest.hexdigest()
