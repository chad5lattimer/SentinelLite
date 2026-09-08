"""Comparison and scan engine for SentinelLite.

Per PROJECT_SPEC.md section 10 (Scan Algorithm) and section 29 (Run 4):
    - Load baseline -> enumerate current files -> hash current files ->
      compare file paths -> compare hashes -> generate results.
    - Each file is classified as NEW, MODIFIED, DELETED, UNCHANGED, or
      ERROR (section 6.3 / section 10):
        - NEW: current file exists, baseline does not.
        - DELETED: baseline has the file, current filesystem does not.
        - MODIFIED: both exist, but the SHA-256 hashes differ.
        - UNCHANGED: both exist and the hashes match.
        - ERROR: the file could not be read during the current scan
          (section 7.3) -- it is reported, not silently dropped or
          treated as DELETED.
    - Scan history is persisted so results remain available after the scan
      completes (section 14).

This module builds on ``core.baseline`` (the trust reference) and
``core.filesystem`` (enumeration/hashing) -- it has no GUI or storage-engine
logic of its own beyond delegating to ``storage.repository`` for
persistence. Deciding when to run a scan, showing progress, and rendering
results is a GUI concern (Run 5).
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from core.baseline import Baseline
from core.filesystem import ProgressCallback, scan_directory
from core.models import FileError, FileRecord, ScanStatus
from storage import repository

logger = logging.getLogger(__name__)

__all__ = [
    "ScanResult",
    "ScanSummary",
    "ScanMetadata",
    "compare_to_baseline",
    "run_scan",
    "save_scan",
    "get_scan_results",
    "list_scans",
]


@dataclass(frozen=True)
class ScanResult:
    """The outcome of comparing a single file against the baseline.

    Per PROJECT_SPEC.md section 6.3.
    """

    path: str
    status: ScanStatus
    baseline_hash: str | None = None
    current_hash: str | None = None
    size: int | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class ScanSummary:
    """Aggregate counts for a completed scan (PROJECT_SPEC.md section 12)."""

    modified: int = 0
    new: int = 0
    deleted: int = 0
    unchanged: int = 0
    errors: int = 0

    @property
    def total(self) -> int:
        return self.modified + self.new + self.deleted + self.unchanged + self.errors

    @classmethod
    def from_results(cls, results: Iterable[ScanResult]) -> "ScanSummary":
        counts = {status: 0 for status in ScanStatus}
        for result in results:
            counts[result.status] += 1
        return cls(
            modified=counts[ScanStatus.MODIFIED],
            new=counts[ScanStatus.NEW],
            deleted=counts[ScanStatus.DELETED],
            unchanged=counts[ScanStatus.UNCHANGED],
            errors=counts[ScanStatus.ERROR],
        )


#: Re-exported for convenience; see ``storage.repository.ScanMetadata``.
ScanMetadata = repository.ScanMetadata


def compare_to_baseline(
    baseline: Baseline,
    current_records: Iterable[FileRecord],
    current_errors: Iterable[FileError] = (),
) -> list[ScanResult]:
    """Compare a baseline against a freshly-enumerated filesystem state.

    This is the pure comparison step of the algorithm in
    PROJECT_SPEC.md section 10 -- it performs no filesystem I/O itself, so
    it can be unit tested directly against in-memory records (section 29's
    acceptance scenario).

    Args:
        baseline: The trust reference to compare against.
        current_records: Files successfully hashed during the current scan.
        current_errors: Files that could not be read during the current
            scan (section 7.3). These become ERROR results rather than
            being mistaken for DELETED files.

    Returns:
        One ``ScanResult`` per path known to either the baseline or the
        current scan, sorted by path for stable, readable output.
    """
    baseline_by_path = {record.path: record for record in baseline.files}
    current_by_path = {record.path: record for record in current_records}
    error_messages = {error.path: error.message for error in current_errors}

    all_paths = set(baseline_by_path) | set(current_by_path) | set(error_messages)

    results: list[ScanResult] = []
    for path in sorted(all_paths):
        baseline_record = baseline_by_path.get(path)

        if path in error_messages:
            results.append(
                ScanResult(
                    path=path,
                    status=ScanStatus.ERROR,
                    baseline_hash=baseline_record.sha256 if baseline_record else None,
                    current_hash=None,
                    size=baseline_record.size if baseline_record else None,
                    error_message=error_messages[path],
                )
            )
            continue

        current_record = current_by_path.get(path)

        if current_record is None:
            results.append(
                ScanResult(
                    path=path,
                    status=ScanStatus.DELETED,
                    baseline_hash=baseline_record.sha256,
                    current_hash=None,
                    size=baseline_record.size,
                )
            )
        elif baseline_record is None:
            results.append(
                ScanResult(
                    path=path,
                    status=ScanStatus.NEW,
                    baseline_hash=None,
                    current_hash=current_record.sha256,
                    size=current_record.size,
                )
            )
        elif baseline_record.sha256 != current_record.sha256:
            results.append(
                ScanResult(
                    path=path,
                    status=ScanStatus.MODIFIED,
                    baseline_hash=baseline_record.sha256,
                    current_hash=current_record.sha256,
                    size=current_record.size,
                )
            )
        else:
            results.append(
                ScanResult(
                    path=path,
                    status=ScanStatus.UNCHANGED,
                    baseline_hash=baseline_record.sha256,
                    current_hash=current_record.sha256,
                    size=current_record.size,
                )
            )

    return results


def run_scan(
    baseline: Baseline,
    progress_callback: ProgressCallback | None = None,
    chunk_size: int | None = None,
) -> list[ScanResult]:
    """Enumerate and hash ``baseline.root_directory`` and compare to ``baseline``.

    This performs the filesystem I/O (section 10: "Enumerate current files
    -> Hash current files") and delegates the comparison to
    ``compare_to_baseline``. It does not persist anything -- call
    ``save_scan`` with the result to write scan history.

    Raises:
        NotADirectoryError: If the baseline's root directory no longer
            exists (propagated from ``core.filesystem.scan_directory``).
    """
    root = Path(baseline.root_directory)
    current_records, current_errors = scan_directory(
        root, progress_callback=progress_callback, chunk_size=chunk_size
    )
    results = compare_to_baseline(baseline, current_records, current_errors)

    summary = ScanSummary.from_results(results)
    logger.info(
        "Scan of %s complete: %d modified, %d new, %d deleted, %d unchanged, %d errors.",
        root,
        summary.modified,
        summary.new,
        summary.deleted,
        summary.unchanged,
        summary.errors,
    )
    return results


def save_scan(
    connection: sqlite3.Connection,
    baseline_id: int,
    started_at: str,
    results: Iterable[ScanResult],
    completed_at: str | None = None,
) -> int:
    """Persist a completed scan and its per-file results as scan history.

    Args:
        connection: An open database connection.
        baseline_id: The baseline this scan was compared against.
        started_at: ISO-8601 timestamp for when the scan began.
        results: The comparison results from ``run_scan`` /
            ``compare_to_baseline``.
        completed_at: ISO-8601 timestamp for scan completion. Defaults to
            now (UTC) if omitted.

    Returns:
        The new scan's id.
    """
    results = list(results)
    summary = ScanSummary.from_results(results)
    resolved_completed_at = completed_at or datetime.now(timezone.utc).isoformat()

    scan_id = repository.insert_scan(
        connection,
        baseline_id=baseline_id,
        started_at=started_at,
        completed_at=resolved_completed_at,
        modified_count=summary.modified,
        new_count=summary.new,
        deleted_count=summary.deleted,
        unchanged_count=summary.unchanged,
        error_count=summary.errors,
        results=results,
    )
    logger.info("Scan #%d saved: %d results against baseline #%d.", scan_id, len(results), baseline_id)
    return scan_id


def get_scan_results(connection: sqlite3.Connection, scan_id: int) -> list[ScanResult]:
    """Return the stored per-file results for a previously saved scan."""
    return repository.get_scan_results(connection, scan_id)


def list_scans(connection: sqlite3.Connection, baseline_id: int | None = None) -> list[ScanMetadata]:
    """Return scan history (most recent first), optionally filtered to one baseline."""
    return repository.list_scans(connection, baseline_id=baseline_id)
