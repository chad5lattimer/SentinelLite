"""Core data models shared across the security engine.

Defining these in one place (rather than duplicating shapes across
`core`, `storage`, `gui`, and `reports`) keeps every layer working from
the same file representation. See PROJECT_SPEC.md section 6 for the data
model this mirrors.

This module contains no filesystem, hashing, or comparison logic -- only
plain data.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FileRecord:
    """A single file as observed on disk, or as stored in a baseline.

    ``path`` is always the file's path relative to the monitored root
    directory, expressed with forward slashes (``Path.as_posix()``), so
    that a baseline created on one platform stays comparable on another
    (PROJECT_SPEC.md section 6.2: "Use relative paths wherever
    possible").
    """

    path: str
    sha256: str
    size: int
    modified_time: float


@dataclass(frozen=True)
class FileError:
    """A file that could not be enumerated or hashed during a scan.

    Recorded instead of raised, so that one unreadable or inaccessible
    file never aborts an entire directory scan (PROJECT_SPEC.md sections
    7.3 and 8.3). ``path`` uses the same relative, forward-slash
    convention as `FileRecord.path`.
    """

    path: str
    message: str
