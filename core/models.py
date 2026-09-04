"""Core data model shared by the hashing, filesystem, baseline, and scan
engine (PROJECT_SPEC.md section 6).

This module intentionally contains no filesystem access or hashing logic --
only plain data structures. Run 2 introduces ``FileRecord`` and
``FileAccessError``; ``ScanStatus``/scan-result structures are added in
Run 4 (core/scanner.py) once comparison logic exists.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FileRecord:
    """A single successfully-hashed file, as described in PROJECT_SPEC.md
    section 6.1/6.2.

    ``path`` is the file's path relative to the monitored root directory,
    using forward slashes (``as_posix()``), so baselines are portable and
    comparable independent of the root's absolute location.
    """

    path: str
    sha256: str
    size: int
    modified_time: float


@dataclass(frozen=True)
class FileAccessError:
    """A file that was discovered during enumeration but could not be
    read/hashed (PROJECT_SPEC.md section 7.3: permission errors and similar
    must not crash the scan -- they are recorded and reported instead).
    """

    path: str
    error: str
