"""Core data models shared by the hashing, filesystem, and baseline layers.

See PROJECT_SPEC.md section 6 (Core Data Model). Only ``FileRecord`` is
defined here for Run 2 -- it is the unit produced by enumerating and
hashing a monitored directory (PROJECT_SPEC.md section 6.1). Scan-result
models (NEW/MODIFIED/DELETED/UNCHANGED/ERROR, section 6.3) belong to the
comparison engine and are added in Run 4 (see PROJECT_SPEC.md section 29)
to avoid expanding this run's scope.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FileRecord:
    """A single file's identity and content fingerprint at a point in time.

    ``path`` is a POSIX-style path (forward slashes) relative to the
    monitored root directory, so baselines remain portable across
    platforms (PROJECT_SPEC.md section 6.2: "Use relative paths wherever
    possible").
    """

    path: str
    sha256: str
    size: int
    modified_time: float
