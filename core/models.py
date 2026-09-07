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


@dataclass(frozen=True)
class Baseline:
    """A cryptographic baseline: the trust reference for later scans.

    Per PROJECT_SPEC.md section 6.2. ``baseline_id`` is ``None`` for a
    baseline that has been created but not yet persisted; the storage
    layer returns a copy with ``baseline_id`` set once saved.

    Attributes:
        baseline_id: Primary key assigned by storage, or ``None`` if this
            baseline has not been saved yet.
        created_at: Creation time, as an ISO 8601 UTC timestamp string.
        root_directory: Absolute path to the directory this baseline was
            created from.
        application_version: SentinelLite version that created the
            baseline (informational; not used for compatibility checks in
            the MVP).
        files: The hashed files that make up this baseline, in the same
            form produced by ``core.filesystem.scan_directory`` (relative
            paths, forward slashes).
    """

    baseline_id: int | None
    created_at: str
    root_directory: str
    application_version: str
    files: tuple[FileRecord, ...]
