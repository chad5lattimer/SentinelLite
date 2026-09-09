"""Scan result export for SentinelLite (PROJECT_SPEC.md section 15).

Writes an already-completed scan's results to CSV or JSON. This module
performs file I/O only -- it contains no hashing, filesystem scanning, or
comparison logic (PROJECT_SPEC.md section 5), and never chooses *where* to
write; callers (the GUI, tests) supply a destination path.

Per section 16 (Logging), every export is logged -- but never the contents
of monitored files, only that an export happened and where it went.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Iterable

from core.scanner import ScanResult, ScanSummary

logger = logging.getLogger(__name__)

__all__ = ["export_csv", "export_json"]

#: Column order for CSV export, per PROJECT_SPEC.md section 15.1.
_CSV_HEADER: tuple[str, ...] = ("status", "path", "baseline_hash", "current_hash", "size", "timestamp")


def export_csv(
    results: Iterable[ScanResult],
    destination: Path,
    *,
    timestamp: str = "",
) -> Path:
    """Write scan results to a CSV file.

    Per PROJECT_SPEC.md section 15.1, the header row is exactly::

        status,path,baseline_hash,current_hash,size,timestamp

    Args:
        results: The per-file scan results to export.
        destination: Path to write. Parent directories are created if
            needed.
        timestamp: Display string for when the scan completed, repeated on
            every row (results themselves carry no per-file timestamp; see
            PROJECT_SPEC.md section 6.3).

    Returns:
        ``destination``, for convenience chaining.
    """
    results = list(results)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with destination.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(_CSV_HEADER)
        for result in results:
            writer.writerow(
                [
                    result.status.value,
                    result.path,
                    result.baseline_hash or "",
                    result.current_hash or "",
                    result.size if result.size is not None else "",
                    timestamp,
                ]
            )

    logger.info("Exported %d scan result(s) to CSV: %s", len(results), destination)
    return destination


def export_json(
    results: Iterable[ScanResult],
    destination: Path,
    *,
    scan_id: int,
    timestamp: str,
    root_directory: str,
) -> Path:
    """Write scan results to a JSON file.

    Per PROJECT_SPEC.md section 15.2, the top-level shape is::

        {
            "scan_id": 1,
            "timestamp": "...",
            "root_directory": "...",
            "summary": {"modified": 3, "new": 7, "deleted": 1,
                        "unchanged": 1273, "errors": 0},
            "results": []
        }

    Args:
        results: The per-file scan results to export.
        destination: Path to write. Parent directories are created if
            needed.
        scan_id: The id of the stored scan these results belong to.
        timestamp: Display string for when the scan completed.
        root_directory: The monitored directory the scan was run against.

    Returns:
        ``destination``, for convenience chaining.
    """
    results = list(results)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    summary = ScanSummary.from_results(results)
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

    with destination.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)
        file.write("\n")

    logger.info("Exported %d scan result(s) to JSON: %s", len(results), destination)
    return destination
