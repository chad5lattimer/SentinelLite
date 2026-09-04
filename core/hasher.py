"""SHA-256 file hashing.

Per PROJECT_SPEC.md section 7:
    - SHA-256 only (via `hashlib`) is used for integrity comparisons --
      never MD5 or SHA-1.
    - Files are hashed incrementally in chunks so large files are never
      loaded fully into memory.
    - Read/permission errors are allowed to propagate as exceptions from
      this module; it is the caller's responsibility (see
      `core.filesystem`) to catch them, log them, and continue the scan
      rather than aborting it (section 7.3).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from config import DEFAULT_HASH_CHUNK_SIZE


def calculate_sha256(file_path: Path, chunk_size: int = DEFAULT_HASH_CHUNK_SIZE) -> str:
    """Return the hex-encoded SHA-256 digest of the file at `file_path`.

    The file is read incrementally in `chunk_size`-byte chunks rather than
    loaded fully into memory (PROJECT_SPEC.md section 7.2). The default
    chunk size (1 MiB) is configured centrally in `config.py`.

    Raises:
        OSError: (or a subclass, e.g. `PermissionError`,
            `FileNotFoundError`) if the file cannot be opened or read.
            Callers must catch this and continue rather than aborting an
            entire scan (PROJECT_SPEC.md section 7.3).
        ValueError: if `chunk_size` is not a positive integer.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer.")

    digest = hashlib.sha256()
    with open(file_path, "rb") as file:
        while chunk := file.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
