"""Report export for SentinelLite scan results (PROJECT_SPEC.md section 15).

Pure serialization -- no GUI, hashing, or filesystem-comparison logic here.
Callers supply already-computed ``core.scanner.ScanResult`` objects; this
module only writes them to CSV or JSON, per PROJECT_SPEC.md section 5's
layering (GUI -> application logic -> security/core logic -> storage;
export is an application-logic concern that sits above the GUI, not inside
it).

The GUI (``gui.results_view``) is expected to be the caller: it already
holds the results and display timestamp for the scan currently on screen.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Iterable

from core.scanner import ScanResult, ScanSummary

logger = logging.getLogger(__name__)

__all__ = ["export_to_csv", "export_to_json"]

#: Column order per PROJECT_SPEC.md section 15.1.
_CSV_HEADER: tuple[str, ...] = ("status", "path", "baseline_hash", "current_hash", "size", "timestamp")


def export_to_csv(
    results: Iterable[ScanResult],
    destination: Path,
    *,
    timestamp: str = "",
) -> Path:
    """Write ``results`` to ``destination`` as CSV (PROJECT_SPEC.md section 15.1).

    Args:
        results: The scan results to export.
        destination: Output file path. Parent directories are created if
            needed.
        timestamp: Display timestamp written into every row's
            ``timestamp`` column (there is no per-file timestamp in
            ``ScanResult`` -- see the Run 5 status report's documented
            simplification, which this export mirrors for consistency with
            what the results table already shows).

    Returns:
        ``destination``, for convenient chaining.

    Raises:
        OSError: If the file cannot be written (e.g. permission denied,
            disk full). Callers (the GUI) are expected to catch this and
            show a user-friendly message per section 18.
    """
    results = list(results)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
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

    logger.info("Exported %d scan result(s) to CSV: %s", len(results), destination)
    return destination


def export_to_json(
    results: Iterable[ScanResult],
    destination: Path,
    *,
    scan_id: int,
    timestamp: str,
    root_directory: str,
) -> Path:
    """Write ``results`` to ``destination`` as JSON (PROJECT_SPEC.md section 15.2).

    Args:
        results: The scan results to export.
        destination: Output file path. Parent directories are created if
            needed.
        scan_id: The persisted scan's id (``storage.repository.insert_scan``).
        timestamp: Display timestamp for the scan (see ``export_to_csv``).
        root_directory: The monitored directory the scan was run against.

    Returns:
        ``destination``, for convenient chaining.

    Raises:
        OSError: If the file cannot be written. See ``export_to_csv``.
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

    logger.info("Exported %d scan result(s) to JSON: %s", len(results), destination)
    return destination
