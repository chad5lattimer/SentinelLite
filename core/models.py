"""Core data models for SentinelLite.

Defines the data structures shared across the hashing, filesystem, baseline,
and scanner modules, per PROJECT_SPEC.md section 6 (Core Data Model).

These are plain dataclasses with no filesystem, hashing, or GUI logic --
they exist purely to describe shape and shared vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class FileRecord:
    """A single hashed file, as produced by the filesystem/hashing engine.

    Attributes:
        path: Path to the file, relative to the monitored root directory.
            Stored using forward slashes so baselines are portable across
            operating systems (PROJECT_SPEC.md section 6.2).
        sha256: Hex-encoded SHA-256 digest of the file's contents.
        size: File size in bytes.
        modified_time: Last-modified time as a POSIX timestamp
            (``os.stat().st_mtime``).
    """

    path: str
    sha256: str
    size: int
    modified_time: float


class ScanStatus(str, Enum):
    """The outcome of comparing a single file against the baseline.

    Per PROJECT_SPEC.md section 6.3 / section 10.
    """

    NEW = "NEW"
    MODIFIED = "MODIFIED"
    DELETED = "DELETED"
    UNCHANGED = "UNCHANGED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class FileError:
    """A file that could not be read/hashed during enumeration.

    Recorded separately from FileRecord so a single unreadable file cannot
    prevent the rest of the scan from proceeding (PROJECT_SPEC.md
    section 7.3 / section 8.3).
    """

    path: str
    message: str
