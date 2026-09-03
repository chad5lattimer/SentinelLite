"""Core data models shared across the SentinelLite engine.

Per PROJECT_SPEC.md section 6.1, each monitored file is represented as a
small, typed structure. This module intentionally contains no filesystem
or hashing logic -- see ``core/filesystem.py`` and ``core/hasher.py``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FileRecord:
    """A single monitored file's identity, hash, and metadata.

    Attributes:
        path: Path to the file, relative to the monitored root directory
            (POSIX-style separators, per PROJECT_SPEC.md section 6.2, so
            baselines are portable across platforms).
        sha256: Lowercase hex-encoded SHA-256 digest of the file contents.
        size: File size in bytes.
        modified_time: Last-modified time as a POSIX timestamp (seconds
            since the epoch), as returned by ``os.stat``.
    """

    path: str
    sha256: str
    size: int
    modified_time: float


@dataclass(frozen=True)
class FileError:
    """A file that could not be enumerated or hashed.

    Kept separate from ``FileRecord`` so that callers must explicitly
    handle unreadable files rather than a hash silently becoming an empty
    string (see PROJECT_SPEC.md section 7.3 -- errors must not crash a
    scan and must be reported to the user).

    Attributes:
        path: Path to the file, relative to the monitored root directory.
        message: Human-readable description of what went wrong.
    """

    path: str
    message: str
