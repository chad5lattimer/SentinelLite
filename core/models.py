"""Core data models for SentinelLite.

Defines the data structures shared across the filesystem/hashing engine
(Run 2), the baseline system (Run 3), and the scan/comparison engine
(Run 4). Kept as plain, typed dataclasses with no filesystem, hashing, or
GUI logic of their own -- see PROJECT_SPEC.md section 6 (Core Data Model).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class FileRecord:
    """A single file's identity and integrity information.

    ``path`` is a forward-slash-separated path relative to the monitored
    root directory (per PROJECT_SPEC.md section 6.2: "Use relative paths
    wherever possible"), so baselines remain portable if the monitored
    directory is moved or accessed from a different OS.
    """

    path: str
    sha256: str
    size: int
    modified_time: float


@dataclass(frozen=True)
class FileAccessError:
    """A file that was enumerated but could not be read/hashed.

    Per PROJECT_SPEC.md section 7.3, a hashing failure must not crash the
    scan: the offending file is recorded here (with a user-friendly
    ``message``) so the caller can log it and continue processing the
    remaining files.
    """

    path: str
    message: str


class ScanStatus(str, Enum):
    """The outcome of comparing one file against the baseline.

    Defined here (rather than in core/scanner.py, Run 4) because it is
    part of the shared core data model (PROJECT_SPEC.md section 6.3) and
    ``FileAccessError`` above already maps to ``ERROR``.
    """

    NEW = "NEW"
    MODIFIED = "MODIFIED"
    DELETED = "DELETED"
    UNCHANGED = "UNCHANGED"
    ERROR = "ERROR"
