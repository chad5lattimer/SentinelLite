"""Core data model for SentinelLite.

Per PROJECT_SPEC.md section 6.1, a monitored file is represented by a small,
immutable record capturing its identity and content fingerprint. This module
intentionally contains no filesystem, hashing, or comparison logic -- see
`core/hasher.py` and `core/filesystem.py` for that.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FileRecord:
    """A single file's identity and SHA-256 fingerprint at a point in time.

    Attributes:
        path: Relative, POSIX-style path (forward slashes) from the
            monitored root directory. Relative paths are used, per
            PROJECT_SPEC.md section 6.2, so a baseline built from this
            record remains meaningful even if the monitored directory is
            later moved or accessed from a different absolute location.
        sha256: Hex-encoded SHA-256 digest of the file's contents.
        size: File size in bytes.
        modified_time: Last-modified time as a POSIX timestamp
            (`os.stat().st_mtime`).
    """

    path: str
    sha256: str
    size: int
    modified_time: float
