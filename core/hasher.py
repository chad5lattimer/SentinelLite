"""SHA-256 file hashing.

Implements PROJECT_SPEC.md section 7 (Hashing Requirements): SHA-256 via
the standard-library ``hashlib`` (never MD5/SHA-1), reading files in
configurable-size chunks so large files are never loaded into memory at
once (section 7.2).

This module only computes hashes. It does not decide how to react to an
unreadable file -- callers (see ``core.filesystem``) catch the ``OSError``
this raises and record an ERROR result instead of crashing the scan
(section 7.3).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from config import DEFAULT_HASH_CHUNK_SIZE


def calculate_sha256(file_path: Path, chunk_size: int = DEFAULT_HASH_CHUNK_SIZE) -> str:
    """Return the lowercase hex SHA-256 digest of the file at ``file_path``.

    The file is read incrementally in ``chunk_size``-byte chunks (default
    1 MiB, per PROJECT_SPEC.md section 7.2) rather than being loaded into
    memory in full.

    Raises:
        ValueError: if ``chunk_size`` is not a positive integer.
        OSError: (or a subclass, e.g. ``PermissionError``,
            ``FileNotFoundError``) if the file cannot be opened or read.
            Callers are responsible for handling this per section 7.3.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer")

    digest = hashlib.sha256()
    with open(file_path, "rb") as file:
        while chunk := file.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
