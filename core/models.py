"""Core data model for SentinelLite.

Defines the small set of value objects shared by the filesystem/hashing
engine and (in later runs) the baseline and scan-comparison engines. See
PROJECT_SPEC.md section 6 for the canonical shapes these mirror.

This module contains no filesystem or hashing logic -- only plain data.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FileRecord:
    """A single hashed file, as produced by the filesystem/hashing engine.

    Mirrors PROJECT_SPEC.md section 6.1:

        FileRecord:
            path: str
            sha256: str
            size: int
            modified_time: float

    ``path`` is a forward-slash-normalized path *relative* to the scanned
    root directory (see section 6.2: "Use relative paths wherever
    possible."), so baselines remain portable if the monitored directory
    is moved or accessed from a different mount point/drive letter.
    """

    path: str
    sha256: str
    size: int
    modified_time: float


@dataclass(frozen=True)
class FileAccessError:
    """A file that could not be enumerated or hashed.

    Per PROJECT_SPEC.md section 7.3 / 8.3, inaccessible files must not
    crash a scan -- they are recorded and logged instead, and the caller
    continues processing the remaining files. ``path`` uses the same
    relative, forward-slash-normalized form as `FileRecord.path`.
    """

    path: str
    message: str
