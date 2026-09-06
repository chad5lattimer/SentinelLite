"""Core data models for SentinelLite.

Defines the shared data shapes used across the hashing, baseline, and
scanning subsystems. This module contains no filesystem or hashing
logic -- it only defines structures, per PROJECT_SPEC.md section 6.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FileRecord:
    """A single monitored file's identity and integrity metadata.

    See PROJECT_SPEC.md section 6.1/6.2.

    Attributes:
        path: Path to the file, relative to the monitored root directory,
            using forward slashes for cross-platform consistency.
        sha256: Lowercase hex-encoded SHA-256 digest of the file's contents.
        size: File size in bytes.
        modified_time: File's last-modified time as a POSIX timestamp.
    """

    path: str
    sha256: str
    size: int
    modified_time: float
