"""SHA-256 file hashing (PROJECT_SPEC.md section 7).

File integrity monitoring's fundamental security mechanism: files are
never compared by name, size, or modification time alone -- content
integrity is established via a cryptographic hash. MD5 and SHA-1 must
never be used for integrity comparisons (section 7.1).

Files are hashed incrementally in fixed-size chunks (section 7.2) so
memory usage stays constant regardless of file size.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from config import DEFAULT_HASH_CHUNK_SIZE


def calculate_sha256(
    file_path: Path,
    chunk_size: int = DEFAULT_HASH_CHUNK_SIZE,
) -> str:
    """Return the lowercase hex SHA-256 digest of ``file_path``.

    Reads the file incrementally in ``chunk_size``-byte chunks (default
    1 MiB) rather than loading it entirely into memory, so large files
    do not cause excessive memory usage.

    Raises whatever ``OSError`` subclass the filesystem reports (e.g.
    ``PermissionError``, ``FileNotFoundError``) if the file cannot be
    read. Callers scanning a directory tree are responsible for catching
    these and recording an ERROR result rather than letting the scan
    crash (section 7.3) -- see ``core.filesystem.scan_directory``.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive number of bytes.")

    digest = hashlib.sha256()
    with open(file_path, "rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
