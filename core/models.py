"""Core data model for SentinelLite.

Defines the shared, GUI-free data structures used throughout the security
engine. See PROJECT_SPEC.md section 6 for the canonical field definitions.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FileRecord:
    """A single hashed file, as produced by the filesystem/hashing engine.

    Attributes:
        path: Path to the file, relative to the monitored root directory,
            using forward slashes (POSIX style) regardless of platform so
            that baselines are portable and stable to compare.
        sha256: Lowercase hex-encoded SHA-256 digest of the file contents.
        size: File size in bytes, as reported by the filesystem.
        modified_time: Last-modified time as a POSIX timestamp (seconds
            since the epoch), matching `os.stat().st_mtime`.
    """

    path: str
    sha256: str
    size: int
    modified_time: float


@dataclass(frozen=True)
class FileAccessError:
    """Records a file that could not be read/hashed during enumeration.

    Per PROJECT_SPEC.md section 7.3, an unreadable file must not abort a
    scan or baseline creation -- it is recorded here (and logged) so the
    caller can continue processing the remaining files and inform the user
    afterward.
    """

    path: str
    message: str
