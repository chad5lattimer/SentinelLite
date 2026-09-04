"""Core data structures shared by the hashing, baseline, and scan engines.

These are plain data containers (per PROJECT_SPEC.md section 6) with no
filesystem, hashing, or GUI logic attached. Keeping them dependency-free
makes the rest of `core/` easy to test in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class FileRecord:
    """A single hashed file, as produced by the filesystem/hashing engine
    and stored in a baseline.

    ``path`` is a forward-slash relative path from the monitored root
    directory (see PROJECT_SPEC.md section 6.2: "Use relative paths
    wherever possible").
    """

    path: str
    sha256: str
    size: int
    modified_time: float


@dataclass(frozen=True)
class FileAccessError:
    """A file that was enumerated but could not be read/hashed.

    Per PROJECT_SPEC.md section 7.3, unreadable files must not crash a
    baseline creation or scan; instead they are recorded and reported to
    the user once the operation finishes.
    """

    path: str
    message: str


class ScanStatus(str, Enum):
    """The outcome of comparing one file against the baseline
    (PROJECT_SPEC.md section 6.3 / section 10)."""

    NEW = "NEW"
    MODIFIED = "MODIFIED"
    DELETED = "DELETED"
    UNCHANGED = "UNCHANGED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class ScanResult:
    """The comparison outcome for a single file within one scan."""

    path: str
    status: ScanStatus
    baseline_hash: str | None = None
    current_hash: str | None = None
    size: int | None = None
    modified_time: float | None = None
    error_message: str | None = None
