"""Core data model shared by the hashing, filesystem, baseline, and scan
engine (PROJECT_SPEC.md section 6).

This module intentionally contains no filesystem or hashing logic -- it
only defines the plain data structures that the rest of ``core`` produces
and consumes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class FileRecord:
    """A single file's identity and integrity fingerprint.

    ``path`` is stored relative to the monitored root directory (using
    forward slashes) so that baselines remain portable, per
    PROJECT_SPEC.md section 6.2 ("Use relative paths wherever possible.").
    """

    path: str
    sha256: str
    size: int
    modified_time: float


@dataclass(frozen=True)
class FileAccessError:
    """Records a file that could not be enumerated or hashed.

    Per PROJECT_SPEC.md section 7.3, a file that cannot be read must not
    crash the scan: it is recorded here (and logged) so the scan/baseline
    process can continue with the remaining files and inform the user
    afterward.
    """

    path: str
    message: str


class ScanStatus(str, Enum):
    """Possible comparison outcomes for a single file (section 6.3)."""

    NEW = "NEW"
    MODIFIED = "MODIFIED"
    DELETED = "DELETED"
    UNCHANGED = "UNCHANGED"
    ERROR = "ERROR"
