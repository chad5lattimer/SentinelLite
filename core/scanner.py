"""Filesystem-to-baseline comparison (scan) engine for SentinelLite.

Per PROJECT_SPEC.md section 10 (Scan Algorithm) and section 29 (Run 4):

    Load baseline
          v
    Enumerate current files
          v
    Hash current files
          v
    Compare file paths
          v
    Compare hashes
          v
    Generate results

Each file ends up in exactly one of five states (section 6.3 / section 10):
    - NEW: exists now, not in baseline.
    - DELETED: in baseline, missing now.
    - MODIFIED: exists in both, but the SHA-256 hashes differ.
    - UNCHANGED: exists in both, hashes match.
    - ERROR: could not be read during this scan (section 7.3) -- recorded
      rather than aborting the scan.

A scan is persisted as one ``scans`` row plus one ``scan_results`` row per
file (PROJECT_SPEC.md section 14), so scan history accumulates independently
of the baseline it was run against. This module has no GUI or storage
schema knowledge beyond calling ``storage.repository``; background-thread
integration is a Run 5 concern.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from core.baseline import Baseline
from core.filesystem import ProgressCallback, scan_directory
from core.models import FileRecord, ScanStatus
from storage import repository

logger = logging.getLogger(__name__)

__all__ = [
    "ScanFileResult",
    "ScanSummary",
    "run_scan",
]


@dataclass(frozen=True)
class ScanFileResult:
    """The outcome of comparing a single file against the baseline.

    Per PROJECT_SPEC.md section 6.3. Only the fields relevant to ``status``
    are populated -- e.g. a DELETED file has no ``current_hash``, and an
    ERROR result has neither hash.
    """

    path: str
    status: ScanStatus
    baseline_hash: str | None = None
    current_hash: str | None = None
    size: int | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class ScanSummary:
    """A completed scan: every per-file result plus aggregate counts.

    ``scan_id`` is ``None`` only for a summary that has not been persisted
    (not currently produced by ``run_scan``, but kept for symmetry with
    ``core.baseline.Baseline`` and to ease future in-memory previews).
    """

    scan_id: int | None
    baseline_id: int
    started_at: str
    completed_at: str
    results: tuple[ScanFileResult, ...] = field(default_factory=tuple)

    @property
    def modified_count(self) -> int:
        return sum(1 for result in self.results if result.status == ScanStatus.MODIFIED)

    @property
    def new_count(self) -> int:
        return sum(1 for result in self.results if result.status == ScanStatus.NEW)

    @property
    def deleted_count(self) -> int:
        return sum(1 for result in self.results if result.status == ScanStatus.DELETED)

    @property
    def unchanged_count(self) -> int:
        return sum(1 for result in self.results if result.status == ScanStatus.UNCHANGED)

    @property
    def error_count(self) -> int:
        return sum(1 for result in self.results if result.status == ScanStatus.ERROR)

    @property
    def has_changes(self) -> bool:
        """Whether anything the user should look at was detected.

        Per PROJECT_SPEC.md section 11.2, "no changes" means only that
        MODIFIED/NEW/DELETED counts are zero -- errors are reported
        separately (section 24: "Scan Completed With Errors") rather than
        folded into "changes detected".
        """
        return self.modified_count > 0 or self.new_count > 0 or self.deleted_count > 0


def _compare_file_states(
    baseline_files: dict[str, FileRecord],
    current_files: dict[str, FileRecord],
) -> list[ScanFileResult]:
    """Classify every path present in either the baseline or the current
    scan into NEW / DELETED / MODIFIED / UNCHANGED, per section 10."""
    results: list[ScanFileResult] = []

    for path in sorted(set(baseline_files) | set(current_files)):
        baseline_record = baseline_files.get(path)
        current_record = current_files.get(path)

        if baseline_record is None and current_record is not None:
            # CURRENT = YES, BASELINE = NO -> NEW
            results.append(
                ScanFileResult(
                    path=path,
                    status=ScanStatus.NEW,
                    current_hash=current_record.sha256,
                    size=current_record.size,
                )
            )
        elif baseline_record is not None and current_record is None:
            # CURRENT = NO, BASELINE = YES -> DELETED
            results.append(
                ScanFileResult(
                    path=path,
                    status=ScanStatus.DELETED,
                    baseline_hash=baseline_record.sha256,
                    size=baseline_record.size,
                )
            )
        else:
            assert baseline_record is not None and current_record is not None
            if baseline_record.sha256 != current_record.sha256:
                status = ScanStatus.MODIFIED  # HASHES DIFFER
            else:
                status = ScanStatus.UNCHANGED  # HASHES MATCH
            results.append(
                ScanFileResult(
                    path=path,
                    status=status,
                    baseline_hash=baseline_record.sha256,
                    current_hash=current_record.sha256,
                    size=current_record.size,
                )
            )

    return results


def run_scan(
    connection: sqlite3.Connection,
    baseline: Baseline,
    root: Path | None = None,
    progress_callback: ProgressCallback | None = None,
    chunk_size: int | None = None,
) -> ScanSummary:
    """Scan a directory and compare it against ``baseline``, persisting the
    result as new scan history.

    Args:
        connection: An open database connection (see ``storage.database``).
        baseline: A previously saved baseline (``baseline.baseline_id`` must
            be set) to compare against.
        root: Directory to scan. Defaults to ``baseline.root_directory`` --
            the directory the baseline itself was created from.
        progress_callback: Forwarded to ``core.filesystem.scan_directory``
            for GUI progress display (PROJECT_SPEC.md section 13).
        chunk_size: Optional hashing chunk-size override.

    Returns:
        A ``ScanSummary`` with a per-file result for every path seen in
        either the baseline or the current scan, plus one ERROR result per
        unreadable file. ``scan_id`` identifies the persisted scan.

    Raises:
        ValueError: If ``baseline`` has not been saved (no ``baseline_id``).
        NotADirectoryError: If the scan root does not exist or is not a
            directory (propagated from ``core.filesystem.scan_directory``).
    """
    if baseline.baseline_id is None:
        raise ValueError("Cannot scan against a baseline that has not been saved.")

    scan_root = Path(root) if root is not None else Path(baseline.root_directory)
    started_at = datetime.now(timezone.utc).isoformat()

    current_records, read_errors = scan_directory(
        scan_root, progress_callback=progress_callback, chunk_size=chunk_size
    )

    baseline_by_path = {record.path: record for record in baseline.files}
    current_by_path = {record.path: record for record in current_records}

    results = _compare_file_states(baseline_by_path, current_by_path)
    results.extend(
        ScanFileResult(path=error.path, status=ScanStatus.ERROR, error_message=error.message)
        for error in read_errors
    )
    results.sort(key=lambda result: result.path)

    completed_at = datetime.now(timezone.utc).isoformat()
    result_tuple = tuple(results)

    scan_id = repository.insert_scan(
        connection,
        baseline_id=baseline.baseline_id,
        started_at=started_at,
        completed_at=completed_at,
        modified_count=sum(1 for r in result_tuple if r.status == ScanStatus.MODIFIED),
        new_count=sum(1 for r in result_tuple if r.status == ScanStatus.NEW),
        deleted_count=sum(1 for r in result_tuple if r.status == ScanStatus.DELETED),
        unchanged_count=sum(1 for r in result_tuple if r.status == ScanStatus.UNCHANGED),
        error_count=sum(1 for r in result_tuple if r.status == ScanStatus.ERROR),
        results=result_tuple,
    )

    summary = ScanSummary(
        scan_id=scan_id,
        baseline_id=baseline.baseline_id,
        started_at=started_at,
        completed_at=completed_at,
        results=result_tuple,
    )

    logger.info(
        "Scan #%d completed for baseline #%d: %d modified, %d new, %d deleted, "
        "%d unchanged, %d errors.",
        scan_id,
        baseline.baseline_id,
        summary.modified_count,
        summary.new_count,
        summary.deleted_count,
        summary.unchanged_count,
        summary.error_count,
    )
    for error in read_errors:
        logger.warning("Scan error reading %s: %s", error.path, error.message)

    return summary
