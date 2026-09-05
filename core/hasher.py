"""SHA-256 file hashing for SentinelLite.

Per PROJECT_SPEC.md section 7:
    - SHA-256 (via ``hashlib``) is the only algorithm used for integrity
      comparisons -- never MD5 or SHA-1.
    - Files are hashed incrementally, in chunks, so large files never need
      to be loaded into memory in full.

This module performs no filesystem enumeration and no error suppression: a
file that cannot be opened or read raises ``OSError`` (or a subclass), and
it is the caller's responsibility (see ``core.filesystem``) to catch that,
log it, and continue -- per section 7.3 hashing itself must not silently
swallow errors.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from config import DEFAULT_HASH_CHUNK_SIZE

#: Algorithm used for all integrity comparisons. Centralized here so the
#: rest of the codebase never hard-codes "sha256" and so it is obvious this
#: is the only algorithm sanctioned by PROJECT_SPEC.md section 7.1.
HASH_ALGORITHM: str = "sha256"


def calculate_sha256(file_path: Path, chunk_size: int = DEFAULT_HASH_CHUNK_SIZE) -> str:
    """Compute the SHA-256 digest of a file, reading it incrementally.

    Args:
        file_path: Path to the file to hash.
        chunk_size: Number of bytes to read per chunk. Defaults to
            ``config.DEFAULT_HASH_CHUNK_SIZE`` (1 MiB), per PROJECT_SPEC.md
            section 7.2.

    Returns:
        The lowercase hex-encoded SHA-256 digest of the file's contents.

    Raises:
        OSError: If the file cannot be opened or read (missing, permission
            denied, etc.). Callers that scan many files are expected to
            catch this per file and continue (PROJECT_SPEC.md section 7.3).
        ValueError: If ``chunk_size`` is not positive.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive number of bytes.")

    digest = hashlib.sha256()
    with open(file_path, "rb") as file:
        while chunk := file.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
