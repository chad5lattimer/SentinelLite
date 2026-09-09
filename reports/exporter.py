"""Report export for SentinelLite (PROJECT_SPEC.md section 15).

Turns already-computed scan results into CSV/JSON files, matching the
exact formats specified:

    - CSV: ``status,path,baseline_hash,current_hash,size,timestamp``
    - JSON: ``{scan_id, timestamp, root_directory, summary{...}, results[]}``

This is a pure formatting/I-O module -- no hashing, comparison, or GUI
logic (PROJECT_SPEC.md section 5). Callers (the GUI, in Run 6) supply the
``core.scanner.ScanResult`` objects already produced by a scan.
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


def export_csv(results: Iterable[ScanResult], destination: Path, *, timestamp: str = "") -> Path:
    """Write ``results`` to ``destination`` as CSV (PROJECT_SPEC.md section 15.1).

    Args:
        results: The per-file scan results to export.
        destination: Output file path. Its parent directory is created if
            necessary.
        timestamp: A single display timestamp applied to every row (the
            scan's completion time), since ``ScanResult`` does not carry a
            per-file timestamp.

    Returns:
        ``destination``, for convenience.
    """
    results = list(results)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with destination.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["status", "path", "baseline_hash", "current_hash", "size", "timestamp"])
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
    scan_id: int | None,
    timestamp: str,
    root_directory: str,
) -> Path:
    """Write ``results`` to ``destination`` as JSON (PROJECT_SPEC.md section 15.2).

    Args:
        results: The per-file scan results to export.
        destination: Output file path. Its parent directory is created if
            necessary.
        scan_id: The persisted scan's database id, or ``None`` if the scan
            was not (yet) saved.
        timestamp: The scan's completion timestamp.
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

    with destination.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)

    logger.info("Exported %d scan result(s) to JSON: %s", len(results), destination)
    return destination
