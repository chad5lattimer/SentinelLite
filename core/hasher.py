"""SHA-256 file hashing utilities.

Implements chunked, incremental hashing per PROJECT_SPEC.md section 7.
Files are never loaded fully into memory -- they are read in
configurable-size chunks instead, so large files do not cause excessive
memory usage (section 34).

Only SHA-256, via the standard-library ``hashlib`` module, is used for
integrity comparisons (section 7.1). MD5/SHA-1 must not be introduced
here.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from config import DEFAULT_HASH_CHUNK_SIZE


class HashError(Exception):
    """Raised when a file cannot be read for hashing.

    Callers (filesystem enumeration, and the scanner in a later run)
    catch this to record an ERROR result and continue processing the
    remaining files, per PROJECT_SPEC.md section 7.3 -- a single
    unreadable file must never abort a scan.
    """


def calculate_sha256(file_path: Path, chunk_size: int = DEFAULT_HASH_CHUNK_SIZE) -> str:
    """Calculate the SHA-256 hash of ``file_path``, reading incrementally.

    Args:
        file_path: Path to the file to hash.
        chunk_size: Number of bytes to read per chunk. Defaults to the
            application-wide default (1 MiB, see PROJECT_SPEC.md
            section 7.2).

    Returns:
        The lowercase hex-encoded SHA-256 digest of the file's contents.

    Raises:
        HashError: If the file cannot be opened or read (e.g. permission
            denied, the file was removed mid-scan, or another I/O error
            occurred). The original exception is chained via ``__cause__``
            for logging/diagnostics.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer")

    sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as file:
            while chunk := file.read(chunk_size):
                sha256.update(chunk)
    except OSError as exc:
        raise HashError(f"Unable to read file: {file_path}") from exc

    return sha256.hexdigest()
