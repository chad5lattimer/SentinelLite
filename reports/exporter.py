"""CSV/JSON scan-result export for SentinelLite (PROJECT_SPEC.md section 15).

Per the layered architecture (section 5), this module performs pure
formatting/serialization only -- no hashing, filesystem, or comparison
logic, and no GUI dependency. Callers (the GUI, in Run 6) supply
already-computed ``core.scanner.ScanResult`` objects plus scan metadata and
a destination path; this module writes the file.
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

#: Column order for CSV export, per PROJECT_SPEC.md section 15.1:
#: "status,path,baseline_hash,current_hash,size,timestamp"
_CSV_HEADER: tuple[str, ...] = ("status", "path", "baseline_hash", "current_hash", "size", "timestamp")


def export_csv(
    results: Iterable[ScanResult],
    destination: Path,
    *,
    timestamp: str = "",
) -> Path:
    """Write ``results`` to ``destination`` as CSV.

    Per PROJECT_SPEC.md section 15.1, every row uses the same scan
    ``timestamp`` (scan results don't carry a per-file timestamp of their
    own -- see ``core.scanner.ScanResult``).

    Args:
        results: The per-file scan outcomes to export.
        destination: File path to write. Parent directories are created if
            necessary.
        timestamp: A display or ISO-8601 timestamp for the scan these
            results belong to, written into every row.

    Returns:
        ``destination``, for convenience.
    """
    results = list(results)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
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
    """Write ``results`` and scan metadata to ``destination`` as JSON.

    Per PROJECT_SPEC.md section 15.2, the document shape is::

        {
            "scan_id": 1,
            "timestamp": "...",
            "root_directory": "...",
            "summary": {
                "modified": 3, "new": 7, "deleted": 1,
                "unchanged": 1273, "errors": 0
            },
            "results": []
        }

    Args:
        results: The per-file scan outcomes to export.
        destination: File path to write. Parent directories are created if
            necessary.
        scan_id: The stored scan's database id (``storage.repository``).
        timestamp: A display or ISO-8601 timestamp for the scan.
        root_directory: The monitored directory the scan was run against.

    Returns:
        ``destination``, for convenience.
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

    with destination.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")

    logger.info("Exported %d scan result(s) to JSON: %s", len(results), destination)
    return destination
