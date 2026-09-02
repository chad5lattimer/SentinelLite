"""Core data models for SentinelLite.

Defines the data structures shared across the security/core layer, per
PROJECT_SPEC.md section 6. Only the file-record model is defined here in
Run 2 (Hashing and Filesystem Engine); baseline and scan-result
structures are added in Run 3 (core/baseline.py) and Run 4
(core/scanner.py) respectively, once the systems that produce and
consume them exist. Adding them early would expand this run's scope
without anything to exercise them (see PROJECT_SPEC.md section 38).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FileRecord:
    """A single file's identity and integrity information.

    Mirrors PROJECT_SPEC.md section 6.1. ``path`` is a forward-slash
    path relative to the directory that was enumerated (see
    ``core.filesystem.build_file_records``), which keeps records
    portable across platforms and directly usable as a baseline
    ``relative_path`` value in Run 3.
    """

    path: str
    sha256: str
    size: int
    modified_time: float
