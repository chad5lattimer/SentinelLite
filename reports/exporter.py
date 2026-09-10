"""Scan result export for SentinelLite (PROJECT_SPEC.md section 15, Run 6).

Writes an already-completed scan's results to CSV and JSON so a user can
keep or share evidence of a scan outside the application. This module
performs no hashing, filesystem, or comparison logic of its own
(PROJECT_SPEC.md section 5) -- it only serializes ``core.scanner.ScanResult``
objects that a scan already produced, plus the summary counts derived from
them.

Per PROJECT_SPEC.md section 6.3 / section 12, ``ScanResult`` has no
per-file timestamp (only the scan as a whole does -- see the Run 5 status
report's notes on the results table). Both export functions therefore take
the scan's completion timestamp as a parameter and apply it to every row,
matching the same simplification already used by ``gui.results_view``.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Iterable

from core.scanner import ScanResult, ScanSummary

logger = logging.getLogger(__name__)

__all__ = ["CSV_FIELDNAMES", "default_export_filename", "export_csv", "export_json"]

#: Column order for CSV export, per PROJECT_SPEC.md section 15.1:
#: "status,path,baseline_hash,current_hash,size,timestamp".
CSV_FIELDNAMES: tuple[str, ...] = ("status", "path", "baseline_hash", "current_hash", "size", "timestamp")


def default_export_filename(scan_id: int, timestamp: str, extension: str) -> str:
    """Return a filesystem-safe default filename for a scan export.

    e.g. ``sentinellite_scan_12_2026-09-08T121500Z.csv``. ``timestamp`` is
    expected to be an ISO-8601 string; characters that are awkward or
    invalid in Windows filenames (``:``) are stripped.
    """
    safe_timestamp = timestamp.replace("+00:00", "Z").replace(":", "")
    return f"sentinellite_scan_{scan_id}_{safe_timestamp}.{extension}"


def export_csv(results: Iterable[ScanResult], destination: Path, *, timestamp: str = "") -> Path:
    """Write ``results`` to ``destination`` as CSV.

    Per PROJECT_SPEC.md section 15.1. Creates the parent directory if
    necessary (exports may target a not-yet-created location, e.g. a fresh
    ``%LOCALAPPDATA%\\SentinelLite\\exports`` directory).

    Returns:
        ``destination``, for convenience when chaining into a status message.
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with destination.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "status": result.status.value,
                    "path": result.path,
                    "baseline_hash": result.baseline_hash or "",
                    "current_hash": result.current_hash or "",
                    "size": result.size if result.size is not None else "",
                    "timestamp": timestamp,
                }
            )

    logger.info("Exported scan results to CSV: %s", destination)
    return destination


def export_json(
    results: Iterable[ScanResult],
    destination: Path,
    *,
    scan_id: int,
    timestamp: str,
    root_directory: str,
) -> Path:
    """Write ``results`` to ``destination`` as JSON.

    Per PROJECT_SPEC.md section 15.2::

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

    Returns:
        ``destination``, for convenience when chaining into a status message.
    """
    results = list(results)
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

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)

    logger.info("Exported scan results to JSON: %s", destination)
    return destination
