"""Core data model for SentinelLite.

Defines the plain data structures shared across the security/core layer
(hashing, filesystem enumeration, baseline, scanning) per PROJECT_SPEC.md
section 6. These are simple, GUI-independent dataclasses -- no filesystem
or hashing logic lives here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class FileRecord:
    """A single file's identity and content fingerprint at a point in time.

    ``path`` is a relative, POSIX-style path (forward slashes) from the
    monitored root directory, per PROJECT_SPEC.md section 6.2 ("Use
    relative paths wherever possible"). Storing relative, slash-normalized
    paths keeps baselines portable across machines/drive letters.
    """

    path: str
    sha256: str
    size: int
    modified_time: float


@dataclass(frozen=True)
class FileError:
    """A file that could not be enumerated or hashed.

    Per PROJECT_SPEC.md section 7.3, unreadable files must not crash a
    scan: they are recorded and reported instead. ``path`` uses the same
    relative, slash-normalized convention as :class:`FileRecord`.
    """

    path: str
    message: str


class ScanStatus(str, Enum):
    """Per-file comparison outcome, per PROJECT_SPEC.md section 6.3."""

    NEW = "NEW"
    MODIFIED = "MODIFIED"
    DELETED = "DELETED"
    UNCHANGED = "UNCHANGED"
    ERROR = "ERROR"
