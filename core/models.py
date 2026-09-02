"""Core data models shared across the SentinelLite engine.

These are plain, storage/GUI-agnostic dataclasses. Per PROJECT_SPEC.md
section 5, the GUI must never construct or interpret these directly for
security logic -- they flow from `core` (and later `storage`) outward.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FileRecord:
    """A single file's identity and integrity fingerprint.

    Per PROJECT_SPEC.md section 6.1/6.2. `path` is relative to the
    monitored root directory and uses forward slashes regardless of
    platform, so baselines remain portable and comparable.
    """

    path: str
    sha256: str
    size: int
    modified_time: float
