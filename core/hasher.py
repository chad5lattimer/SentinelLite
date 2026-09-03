"""SHA-256 file hashing utilities.

Per PROJECT_SPEC.md section 7:
    - SHA-256 (via ``hashlib``) is the only algorithm used for integrity
      comparisons -- never MD5 or SHA-1.
    - Files are hashed incrementally in chunks so large files never need
      to be loaded into memory at once.
    - A file that cannot be read must not crash the caller; instead the
      failure is raised as ``FileHashError`` so callers (e.g.
      ``core/filesystem.py``) can record an ERROR result and continue.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from config import DEFAULT_HASH_CHUNK_SIZE


class FileHashError(Exception):
    """Raised when a file cannot be read for hashing.

    Carries the offending path and the underlying OS error so callers can
    log details while still presenting a user-friendly message
    (PROJECT_SPEC.md section 18).
    """

    def __init__(self, path: Path, original_error: OSError) -> None:
        self.path = path
        self.original_error = original_error
        super().__init__(f"Unable to read file: {path} ({original_error})")


def calculate_sha256(
    file_path: Path,
    chunk_size: int = DEFAULT_HASH_CHUNK_SIZE,
) -> str:
    """Compute the SHA-256 digest of a file's contents.

    Reads the file incrementally in ``chunk_size``-byte chunks (default
    1 MiB, per PROJECT_SPEC.md section 7.2) so memory usage does not grow
    with file size.

    Args:
        file_path: Path to the file to hash.
        chunk_size: Number of bytes to read per chunk. Must be positive.

    Returns:
        The lowercase hex-encoded SHA-256 digest.

    Raises:
        FileHashError: If the file cannot be opened or read (missing,
            permission denied, or any other OS-level error).
        ValueError: If ``chunk_size`` is not positive.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive number of bytes")

    digest = hashlib.sha256()
    try:
        with open(file_path, "rb") as file:
            while chunk := file.read(chunk_size):
                digest.update(chunk)
    except OSError as exc:
        raise FileHashError(file_path, exc) from exc

    return digest.hexdigest()
