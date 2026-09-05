"""Core data models shared across the SentinelLite engine.

Implements the data model described in PROJECT_SPEC.md section 6. Kept
deliberately small: these are plain, immutable dataclasses with no
filesystem, hashing, or storage logic of their own.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FileRecord:
    """A single file's identity and integrity fingerprint.

    ``path`` is always a relative, forward-slash ("/") separated path from
    the monitored root directory (PROJECT_SPEC.md section 6.2: "Use
    relative paths wherever possible"), so baselines remain portable across
    machines and drive letters.
    """

    path: str
    sha256: str
    size: int
    modified_time: float


@dataclass(frozen=True)
class FileAccessError:
    """A file that was found during enumeration but could not be read.

    Per PROJECT_SPEC.md section 7.3, an unreadable file must not crash the
    scan: it is recorded here (and later surfaced as an ERROR scan result
    in Run 4) instead of raising out of the enumeration/hashing step.
    """

    path: str
    message: str
