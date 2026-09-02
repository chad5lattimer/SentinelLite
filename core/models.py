"""Core data model for SentinelLite.

Defines the small set of typed structures shared by the hashing,
filesystem, baseline, and scanning modules, per PROJECT_SPEC.md section 6.

Only the pieces needed so far (Run 2 -- hashing and filesystem
enumeration) are defined here: ``FileRecord`` for a successfully hashed
file, and ``FileError`` for a file that could not be read. Baseline and
scan-result models (PROJECT_SPEC.md sections 6.2/6.3) are added in the
runs that implement them (Run 3/Run 4) to avoid expanding scope early.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FileRecord:
    """A single hashed file, per PROJECT_SPEC.md section 6.1.

    Attributes:
        path: Path relative to the monitored root directory, using
            forward slashes regardless of platform (see
            ``core.filesystem`` for how this is produced).
        sha256: Hex-encoded SHA-256 digest of the file's contents.
        size: File size in bytes.
        modified_time: Last-modified time as a Unix timestamp
            (``os.stat().st_mtime``).
    """

    path: str
    sha256: str
    size: int
    modified_time: float


@dataclass(frozen=True)
class FileError:
    """A file that was enumerated but could not be read/hashed.

    Per PROJECT_SPEC.md section 7.3 and 8.3, unreadable files must not
    crash a scan -- they are recorded and reported instead.

    Attributes:
        path: Path relative to the monitored root directory (forward
            slashes), matching ``FileRecord.path``.
        message: A short, user-friendly description of the failure.
    """

    path: str
    message: str
