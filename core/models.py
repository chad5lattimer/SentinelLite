"""Core data models for SentinelLite.

Per PROJECT_SPEC.md section 6.1, each monitored file is represented by a
small, immutable record produced by the filesystem/hashing engine
(`core.filesystem`) and consumed by later components (baseline storage in
Run 3, the scan/comparison engine in Run 4).

These models intentionally contain no filesystem, hashing, or GUI logic --
only plain data.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FileRecord:
    """A single file's identity and integrity information.

    Attributes:
        path: Path to the file relative to the monitored root directory,
            using forward slashes regardless of platform (see
            PROJECT_SPEC.md section 6.2, "Use relative paths wherever
            possible").
        sha256: Hex-encoded SHA-256 digest of the file's contents.
        size: File size in bytes.
        modified_time: Last-modified time as a POSIX timestamp
            (``os.stat().st_mtime``).
    """

    path: str
    sha256: str
    size: int
    modified_time: float


@dataclass(frozen=True)
class FileError:
    """A file or directory that could not be processed during enumeration.

    Per PROJECT_SPEC.md sections 7.3 and 8.3, permission errors and unreadable
    files must not crash a scan. Each failure is instead recorded as one of
    these so the caller can log it and inform the user after the scan
    completes.

    Attributes:
        path: Path relative to the monitored root directory (forward
            slashes), or the raw path if it falls outside the root (e.g. a
            directory listing failure).
        message: A short, technical description of the failure, suitable
            for the application log (see PROJECT_SPEC.md section 18 for the
            distinction between log detail and user-facing messages).
    """

    path: str
    message: str
