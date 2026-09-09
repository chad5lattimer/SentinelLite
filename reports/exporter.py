"""Scan result export for SentinelLite (PROJECT_SPEC.md section 15).

Per section 31 (Run 6): users must be able to export scan results to CSV
and JSON. This module contains pure export logic only -- it takes
already-computed ``core.scanner.ScanResult`` objects and writes them to a
file. It performs no hashing, filesystem scanning, or comparison logic,
and no GUI logic (PROJECT_SPEC.md section 5); the GUI is responsible for
choosing a destination path and calling into this module.

Per-file timestamps are not part of ``ScanResult`` (scans record a single
``completed_at`` for the whole scan, not per-file times -- see
``storage`` section 14). Consistent with how Run 5's results table
already displays this, every exported row uses the scan's completion
timestamp.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from core.scanner import ScanResult, ScanSummary

__all__ = ["export_csv", "export_json"]

#: Column order for CSV export, per PROJECT_SPEC.md section 15.1.
_CSV_HEADER: tuple[str, ...] = ("status", "path", "baseline_hash", "current_hash", "size", "timestamp")


def export_csv(results: Iterable[ScanResult], destination: Path, timestamp: str) -> Path:
    """Write ``results`` to ``destination`` as CSV.

    Args:
        results: The scan results to export.
        destination: File path to write. Parent directories are created if
            needed.
        timestamp: Display timestamp applied to every row (the scan's
            completion time -- see module docstring).

    Returns:
        ``destination``, for convenience.
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with destination.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(_CSV_HEADER)
        for result in results:
            writer.writerow(
                (
                    result.status.value,
                    result.path,
                    result.baseline_hash or "",
                    result.current_hash or "",
                    result.size if result.size is not None else "",
                    timestamp,
                )
            )

    return destination


def export_json(
    results: Iterable[ScanResult],
    destination: Path,
    *,
    scan_id: int,
    timestamp: str,
    root_directory: str,
) -> Path:
    """Write ``results`` to ``destination`` as JSON, per section 15.2.

    Args:
        results: The scan results to export.
        destination: File path to write. Parent directories are created if
            needed.
        scan_id: The stored scan's id.
        timestamp: The scan's completion timestamp (ISO-8601).
        root_directory: The monitored directory the scan was run against.

    Returns:
        ``destination``, for convenience.
    """
    results = list(results)
    summary = ScanSummary.from_results(results)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "scan_id": scan_id,
        "timestamp": timestamp,
        "root_directory": root_directory,
        "summary": {
            "modified": summary.modified,
            "new": summary.new,
            "deleted": summary.deleted,
            "unchanged": summary.unchanged,
            "errors": summary.errors,
        },
        "results": [
            {
                "path": result.path,
                "status": result.status.value,
                "baseline_hash": result.baseline_hash,
                "current_hash": result.current_hash,
                "size": result.size,
                "error_message": result.error_message,
            }
            for result in results
        ],
    }

    destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return destination
