"""SHA-256 file hashing (PROJECT_SPEC.md section 7).

Only SHA-256 is used for integrity comparisons -- MD5/SHA-1 are
deliberately not offered. Files are hashed incrementally in fixed-size
chunks so that large files do not need to be loaded into memory at once.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from config import DEFAULT_HASH_CHUNK_SIZE

logger = logging.getLogger(__name__)


class HashError(OSError):
    """Raised when a file cannot be read for hashing.

    Wraps the underlying OSError/PermissionError so callers (the
    filesystem enumeration layer) can catch a single, purpose-specific
    exception type without needing to know every OS-level error class
    that can occur while reading a file.
    """


def calculate_sha256(file_path: Path, chunk_size: int = DEFAULT_HASH_CHUNK_SIZE) -> str:
    """Return the lowercase hex SHA-256 digest of ``file_path``.

    The file is read incrementally in ``chunk_size``-byte chunks (default
    1 MiB, per PROJECT_SPEC.md section 7.2) so that arbitrarily large
    files do not need to be loaded into memory in full.

    Raises:
        HashError: if the file cannot be opened or read (e.g. it does not
            exist, permission is denied, or it disappears mid-read). The
            caller is expected to catch this, record an ERROR result, and
            continue processing remaining files -- per section 7.3, a
            single unreadable file must never crash a scan.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive number of bytes.")

    digest = hashlib.sha256()
    try:
        with open(file_path, "rb") as handle:
            while chunk := handle.read(chunk_size):
                digest.update(chunk)
    except OSError as exc:
        logger.warning("Unable to read file for hashing: %s (%s)", file_path, exc)
        raise HashError(f"Unable to read file: {file_path}") from exc

    return digest.hexdigest()
