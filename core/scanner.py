"""Comparison and scan engine for SentinelLite.

Per PROJECT_SPEC.md section 10 (Scan Algorithm) and section 29 (Run 4):

    Load baseline -> Enumerate current files -> Hash current files ->
    Compare file paths -> Compare hashes -> Generate results

This module contains the pure comparison logic (``compare_to_baseline``),
independently testable without any filesystem or database access, plus the
orchestration (``run_scan``) that enumerates the monitored directory,
compares it against a loaded ``core.baseline.Baseline``, and persists the
outcome as scan history via ``storage.repository``.

GUI wiring (Scan Now button, progress bar, background thread) is deferred
to Run 5, per the scope-control rule (PROJECT_SPEC.md section 38).
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from core.baseline import Baseline
from core.filesystem import ProgressCallback, scan_directory
from core.models import FileError, FileRecord, ScanStatus
from storage import repository

logger = logging.getLogger(__name__)

__all__ = [
    "ScanResult",
    "ScanSummary",
    "compare_to_baseline",
    "run_scan",
]


@dataclass(frozen=True)
class ScanResult:
    """The outcome of comparing a single file against the baseline.

    Per PROJECT_SPEC.md section 6.3. ``baseline_hash``/``current_hash`` are
    ``None`` when the file does not exist on that side of the comparison.
    """

    path: str
    status: ScanStatus
    baseline_hash: str | None = None
    current_hash: str | None = None
    size: int | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class ScanSummary:
    """Aggregate result counts for a completed scan (PROJECT_SPEC.md section 12)."""

    modified: int = 0
    new: int = 0
    deleted: int = 0
    unchanged: int = 0
    errors: int = 0

    @property
    def total(self) -> int:
        return self.modified + self.new + self.deleted + self.unchanged + self.errors


def _summarize(results: list[ScanResult]) -> ScanSummary:
    counts = {status: 0 for status in ScanStatus}
    for result in results:
        counts[result.status] += 1
    return ScanSummary(
        modified=counts[ScanStatus.MODIFIED],
        new=counts[ScanStatus.NEW],
        deleted=counts[ScanStatus.DELETED],
        unchanged=counts[ScanStatus.UNCHANGED],
        errors=counts[ScanStatus.ERROR],
    )


def compare_to_baseline(
    baseline: Baseline,
    current_records: list[FileRecord],
    current_errors: list[FileError],
) -> tuple[list[ScanResult], ScanSummary]:
    """Compare a freshly-enumerated filesystem state against a baseline.

    Implements PROJECT_SPEC.md section 10:
        - NEW: the file exists now but not in the baseline.
        - DELETED: the baseline has the file but it no longer exists.
        - MODIFIED: both exist, but the SHA-256 hashes differ.
        - UNCHANGED: both exist and the hashes match.
        - ERROR: the file could not be read during this scan. Reported
          instead of NEW/DELETED for that path, since its current state is
          unknown rather than absent (PROJECT_SPEC.md section 7.3).

    This is a pure function -- no filesystem or database access -- so scan
    logic is testable independently of the GUI (section 35).

    Returns:
        A tuple ``(results, summary)``, with ``results`` sorted by path for
        stable, predictable output.
    """
    baseline_by_path = {record.path: record for record in baseline.files}
    current_by_path = {record.path: record for record in current_records}
    error_paths = {error.path for error in current_errors}

    results: list[ScanResult] = []

    for path, current in current_by_path.items():
        baseline_record = baseline_by_path.get(path)
        if baseline_record is None:
            status = ScanStatus.NEW
            baseline_hash = None
        elif baseline_record.sha256 != current.sha256:
            status = ScanStatus.MODIFIED
            baseline_hash = baseline_record.sha256
        else:
            status = ScanStatus.UNCHANGED
            baseline_hash = baseline_record.sha256

        results.append(
            ScanResult(
                path=path,
                status=status,
                baseline_hash=baseline_hash,
                current_hash=current.sha256,
                size=current.size,
            )
        )

    for path, baseline_record in baseline_by_path.items():
        if path not in current_by_path and path not in error_paths:
            results.append(
                ScanResult(
                    path=path,
                    status=ScanStatus.DELETED,
                    baseline_hash=baseline_record.sha256,
                    current_hash=None,
                    size=baseline_record.size,
                )
            )

    for error in current_errors:
        baseline_record = baseline_by_path.get(error.path)
        results.append(
            ScanResult(
                path=error.path,
                status=ScanStatus.ERROR,
                baseline_hash=baseline_record.sha256 if baseline_record else None,
                current_hash=None,
                error_message=error.message,
            )
        )

    results.sort(key=lambda result: result.path)
    return results, _summarize(results)


def run_scan(
    connection: sqlite3.Connection,
    root: Path,
    baseline: Baseline,
    progress_callback: ProgressCallback | None = None,
    chunk_size: int | None = None,
) -> tuple[int, list[ScanResult], ScanSummary]:
    """Enumerate ``root``, compare it against ``baseline``, and persist the scan.

    Args:
        connection: An open database connection (see ``storage.database``).
        root: Directory to scan. Must exist and be a directory.
        baseline: A previously saved baseline (``baseline.baseline_id`` must
            be set) to compare against.
        progress_callback: Optional callback forwarded to
            ``core.filesystem.scan_directory`` for GUI progress display
            (PROJECT_SPEC.md section 13).
        chunk_size: Optional override for the hashing chunk size, in bytes.

    Returns:
        A tuple ``(scan_id, results, summary)``.

    Raises:
        ValueError: If ``baseline`` has not been saved (no ``baseline_id``).
        NotADirectoryError: If ``root`` is not an existing directory
            (propagated from ``core.filesystem.scan_directory``).
    """
    if baseline.baseline_id is None:
        raise ValueError("Cannot scan against a baseline that has not been saved.")

    started_at = datetime.now(timezone.utc).isoformat()
    logger.info("Scan started against baseline #%d: %s", baseline.baseline_id, root)

    current_records, current_errors = scan_directory(
        root, progress_callback=progress_callback, chunk_size=chunk_size
    )
    results, summary = compare_to_baseline(baseline, current_records, current_errors)

    completed_at = datetime.now(timezone.utc).isoformat()

    scan_id = repository.insert_scan(
        connection,
        baseline_id=baseline.baseline_id,
        started_at=started_at,
        completed_at=completed_at,
        modified_count=summary.modified,
        new_count=summary.new,
        deleted_count=summary.deleted,
        unchanged_count=summary.unchanged,
        error_count=summary.errors,
        results=(
            (result.path, result.status.value, result.baseline_hash, result.current_hash, result.size, result.error_message)
            for result in results
        ),
    )

    logger.info(
        "Scan #%d completed: %d modified, %d new, %d deleted, %d unchanged, %d errors.",
        scan_id,
        summary.modified,
        summary.new,
        summary.deleted,
        summary.unchanged,
        summary.errors,
    )
    if current_errors:
        for error in current_errors:
            logger.warning("Scan could not read file %s: %s", error.path, error.message)

    return scan_id, results, summary
