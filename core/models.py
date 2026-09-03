"""Core data models shared across the security/core layer.

These are plain, immutable data structures with no filesystem, hashing,
or GUI logic attached -- per PROJECT_SPEC.md section 6 (Core Data Model)
and section 35 (avoid GUI logic inside security modules).

``FileRecord`` and ``FileAccessError`` are produced by ``core.filesystem``
(Run 2). ``ScanStatus`` describes the possible outcomes of comparing a
file against a baseline and is defined here so both the baseline system
(Run 3) and scan engine (Run 4) can share a single definition.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class FileRecord:
    """A single file's identity and integrity fingerprint.

    ``path`` is always a relative, forward-slash-separated path from the
    monitored root (see PROJECT_SPEC.md section 6.2: "Use relative paths
    wherever possible"), so baselines remain portable across machines and
    drive letters.
    """

    path: str
    sha256: str
    size: int
    modified_time: float


@dataclass(frozen=True)
class FileAccessError:
    """A file that could not be read during enumeration/hashing.

    Recorded instead of raised so a single inaccessible file never aborts
    a scan or baseline creation (PROJECT_SPEC.md sections 7.3 and 8.3).
    """

    path: str
    message: str


class ScanStatus(str, Enum):
    """Outcome of comparing one file against the baseline (section 6.3)."""

    NEW = "NEW"
    MODIFIED = "MODIFIED"
    DELETED = "DELETED"
    UNCHANGED = "UNCHANGED"
    ERROR = "ERROR"
