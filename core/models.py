"""Core data models shared across SentinelLite's security/core layer.

Per PROJECT_SPEC.md section 6, these are implemented as simple, frozen
dataclasses. This module contains no hashing, filesystem, or GUI logic --
only data structures.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FileRecord:
    """A single file's identity and integrity fingerprint.

    Per PROJECT_SPEC.md section 6.1/6.2.

    Attributes:
        path: Path to the file, relative to the monitored root directory,
            using forward slashes for cross-platform consistency ("use
            relative paths wherever possible").
        sha256: Hex-encoded SHA-256 digest of the file's contents.
        size: File size in bytes.
        modified_time: Last-modified time as a POSIX timestamp (seconds
            since the epoch), matching `os.stat().st_mtime`.
    """

    path: str
    sha256: str
    size: int
    modified_time: float


@dataclass(frozen=True)
class FileError:
    """A file that could not be read/hashed during enumeration.

    Kept distinct from `FileRecord` (a successfully hashed file) and from
    the `ERROR` scan-result status (introduced with the scan engine in
    Run 4) so that enumeration failures can be surfaced to callers -- and
    eventually to the user and the log -- without being confused with
    either.
    """

    path: str
    message: str
