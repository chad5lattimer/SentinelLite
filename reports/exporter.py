"""Report export for SentinelLite scan results.

Per PROJECT_SPEC.md section 15 (Report Export): completed scan results can
be exported to CSV and JSON. This module is pure formatting/I/O -- per
section 5 ("The GUI must not contain hashing or filesystem comparison
logic"), it has no hashing, filesystem, or comparison logic of its own; it
only writes already-computed ``core.scanner.ScanResult`` objects to disk.

Both functions take a fully-resolved destination path and simply write to
it -- choosing *where* to save (a file dialog, a default exports directory
under ``config.PATHS.exports_dir``) is a GUI concern (Run 6, section 30's
predecessor established that split for hashing/scanning; the same split
applies here).
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

#: CSV column order, per PROJECT_SPEC.md section 15.1.
_CSV_HEADER: tuple[str, ...] = ("status", "path", "baseline_hash", "current_hash", "size", "timestamp")


def export_csv(results: Iterable[ScanResult], destination: Path, *, timestamp: str) -> Path:
    """Write scan results to a CSV file.

    Args:
        results: The per-file results to export (e.g. from ``run_scan`` or
            ``get_scan_results``).
        destination: File path to write. Its parent directory must already
            exist.
        timestamp: A single display timestamp applied to every row -- the
            scan's completion time. ``ScanResult`` has no per-file
            timestamp (that would require expanding the Run 4 data model
            mid-project, which section 38's scope-control rule counsels
            against for an MVP export feature).

    Returns:
        ``destination``, for convenient chaining/return-to-caller.

    Raises:
        OSError: If ``destination`` cannot be written (e.g. permission
            denied, missing parent directory). Callers are expected to
            catch this and show a user-friendly message per section 18.
    """
    destination = Path(destination)
    results = list(results)

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
    """Write scan results to a JSON file.

    Shape, per PROJECT_SPEC.md section 15.2::

        {
            "scan_id": 1,
            "timestamp": "...",
            "root_directory": "...",
            "summary": {"modified": 3, "new": 7, "deleted": 1,
                        "unchanged": 1273, "errors": 0},
            "results": [...]
        }

    Args:
        results: The per-file results to export.
        destination: File path to write. Its parent directory must already
            exist.
        scan_id: The persisted scan's id (``storage.repository.insert_scan``).
        timestamp: The scan's completion time.
        root_directory: The monitored directory the scan was run against.

    Returns:
        ``destination``, for convenient chaining/return-to-caller.

    Raises:
        OSError: If ``destination`` cannot be written. See ``export_csv``.
    """
    destination = Path(destination)
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
                "status": result.status.value,
                "path": result.path,
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
