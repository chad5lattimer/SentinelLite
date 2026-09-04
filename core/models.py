"""Core data models shared across the filesystem, baseline, and scan engines.

See PROJECT_SPEC.md section 6 (Core Data Model). Only the pieces needed by
the current run's engine are defined here -- this module intentionally
contains no filesystem, hashing, or comparison logic.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FileRecord:
    """A single file's identity and content fingerprint at a point in time.

    ``path`` is a forward-slash-separated path, relative to the monitored
    root directory (PROJECT_SPEC.md section 6.2: "Use relative paths
    wherever possible."), so that baselines remain portable across
    machines and drive letters.
    """

    path: str
    sha256: str
    size: int
    modified_time: float


@dataclass(frozen=True)
class FileAccessError:
    """A file that was discovered during enumeration but could not be
    hashed (e.g. a permission error or a file that vanished mid-scan).

    Per PROJECT_SPEC.md section 7.3, such errors must not crash the scan:
    they are collected and reported to the user after the scan completes.
    """

    path: str
    message: str
