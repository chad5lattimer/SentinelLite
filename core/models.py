"""Core data models shared across the security engine.

These are plain, immutable dataclasses with no filesystem or GUI
dependencies (PROJECT_SPEC.md section 6), so they can be constructed and
compared freely in tests and by later baseline/scanner components.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FileRecord:
    """Identity and integrity metadata for a single monitored file.

    ``path`` is a POSIX-style path relative to the monitored root
    directory (e.g. ``"documents/example.txt"``), never an absolute
    path, so baselines remain portable per PROJECT_SPEC.md section 6.2.
    """

    path: str
    sha256: str
    size: int
    modified_time: float


@dataclass(frozen=True)
class FileError:
    """A file that could not be enumerated or hashed during a scan.

    Recorded instead of raising, per PROJECT_SPEC.md section 7.3: a
    single unreadable file must never abort enumeration or hashing.
    """

    path: str
    message: str
