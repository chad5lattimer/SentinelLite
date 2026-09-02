"""Core data model for SentinelLite.

Defines the plain data structures shared by the filesystem/hashing engine
(Run 2), the baseline system (Run 3), and the scan/comparison engine
(Run 4). Kept free of filesystem, hashing, or GUI logic -- see
PROJECT_SPEC.md section 6 ("Core Data Model") for the source requirements.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class FileRecord:
    """A single monitored file, as recorded during enumeration/hashing.

    ``path`` is a forward-slash-separated path relative to the monitored
    root directory (per PROJECT_SPEC.md section 6.2: "Use relative paths
    wherever possible"), so baselines remain portable if the monitored
    directory is moved or accessed from a different machine.
    """

    path: str
    sha256: str
    size: int
    modified_time: float


@dataclass(frozen=True)
class FileError:
    """A file that could not be read/hashed during enumeration.

    Per PROJECT_SPEC.md section 7.3, a hash failure must not crash the
    scan: it is recorded here (and logged) so the scan can continue with
    the remaining files and the user can be informed afterward.
    """

    path: str
    message: str


class ScanStatus(str, Enum):
    """Possible outcomes of comparing one file against the baseline.

    See PROJECT_SPEC.md section 6.3. Defined here (rather than in
    ``core.scanner``) so both the filesystem engine and the future scan
    engine share one definition.
    """

    NEW = "NEW"
    MODIFIED = "MODIFIED"
    DELETED = "DELETED"
    UNCHANGED = "UNCHANGED"
    ERROR = "ERROR"
