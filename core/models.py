"""Core data model for SentinelLite.

Defines the plain data structures shared by the filesystem/hashing engine
and (in later runs) the baseline and scan-comparison engines. These are
pure data containers with no filesystem, hashing, or GUI logic -- see
PROJECT_SPEC.md section 6.

Only the pieces needed by Run 2 (the filesystem/hashing engine) are defined
here: `FileRecord` (section 6.1) and `FileAccessError`, used to report a
file that could not be read without aborting the scan (section 7.3 / 8.3).
The baseline container (section 6.2) and scan-result status model
(section 6.3) are introduced in Runs 3-4, alongside the code that produces
them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FileRecord:
    """A single file's identity and content fingerprint at a point in time.

    Attributes:
        path: Path relative to the monitored root, using forward slashes
            (POSIX-style) regardless of platform, so baselines are portable
            and comparisons are not sensitive to path-separator differences.
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
class FileAccessError:
    """A file (or directory) that could not be read during enumeration.

    Per PROJECT_SPEC.md section 7.3 and 8.3, an unreadable file must not
    crash the scan: it is logged and recorded here so the caller can
    continue processing the remaining files and inform the user afterward.

    Attributes:
        path: Path relative to the monitored root when it could be
            determined, otherwise the raw path as reported by the OS.
        message: Human-readable description of the error (from the
            underlying ``OSError``).
    """

    path: str
    message: str
