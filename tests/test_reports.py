"""Tests for reports.exporter (PROJECT_SPEC.md section 15, section 19 - Reports).

Covers:
    - CSV generation with the exact header from section 15.1.
    - JSON generation with the exact shape from section 15.2.
    - Correct summary counts.
    - Correct file paths.
    - Valid JSON syntax.
"""

from __future__ import annotations

import csv
import json

from core.models import ScanStatus
from core.scanner import ScanResult
from reports.exporter import export_csv, export_json

_RESULTS = [
    ScanResult(
        path="modified.txt",
        status=ScanStatus.MODIFIED,
        baseline_hash="aaa",
        current_hash="bbb",
        size=10,
    ),
    ScanResult(path="new.txt", status=ScanStatus.NEW, current_hash="ccc", size=5),
    ScanResult(path="deleted.txt", status=ScanStatus.DELETED, baseline_hash="ddd", size=8),
    ScanResult(
        path="unchanged.txt",
        status=ScanStatus.UNCHANGED,
        baseline_hash="eee",
        current_hash="eee",
        size=20,
    ),
    ScanResult(path="broken.txt", status=ScanStatus.ERROR, error_message="Permission denied"),
]


def test_export_csv_writes_expected_header_and_rows(tmp_path):
    destination = tmp_path / "exports" / "scan.csv"

    result_path = export_csv(_RESULTS, destination, timestamp="Aug 26, 2026 12:45 AM")

    assert result_path == destination
    assert destination.exists()

    with destination.open(newline="", encoding="utf-8") as file:
        rows = list(csv.reader(file))

    assert rows[0] == ["status", "path", "baseline_hash", "current_hash", "size", "timestamp"]
    assert len(rows) == 1 + len(_RESULTS)

    modified_row = rows[1]
    assert modified_row == [
        "MODIFIED",
        "modified.txt",
        "aaa",
        "bbb",
        "10",
        "Aug 26, 2026 12:45 AM",
    ]

    # NEW has no baseline_hash, DELETED has no current_hash -- both blank, not "None".
    new_row = rows[2]
    assert new_row[2] == ""
    deleted_row = rows[3]
    assert deleted_row[3] == ""


def test_export_csv_creates_parent_directories(tmp_path):
    destination = tmp_path / "a" / "b" / "c" / "scan.csv"
    export_csv([], destination)
    assert destination.exists()


def test_export_json_has_expected_shape_and_valid_syntax(tmp_path):
    destination = tmp_path / "scan.json"

    export_json(
        _RESULTS,
        destination,
        scan_id=42,
        timestamp="2026-08-26T00:45:00+00:00",
        root_directory="/monitored",
    )

    with destination.open(encoding="utf-8") as file:
        payload = json.load(file)  # raises if not valid JSON

    assert payload["scan_id"] == 42
    assert payload["timestamp"] == "2026-08-26T00:45:00+00:00"
    assert payload["root_directory"] == "/monitored"
    assert payload["summary"] == {
        "modified": 1,
        "new": 1,
        "deleted": 1,
        "unchanged": 1,
        "errors": 1,
    }
    assert len(payload["results"]) == len(_RESULTS)

    paths = {entry["path"] for entry in payload["results"]}
    assert paths == {"modified.txt", "new.txt", "deleted.txt", "unchanged.txt", "broken.txt"}

    error_entry = next(entry for entry in payload["results"] if entry["path"] == "broken.txt")
    assert error_entry["status"] == "ERROR"
    assert error_entry["error_message"] == "Permission denied"


def test_export_json_summary_matches_results_regardless_of_order(tmp_path):
    destination = tmp_path / "scan.json"
    export_json(
        list(reversed(_RESULTS)),
        destination,
        scan_id=1,
        timestamp="now",
        root_directory="/monitored",
    )
    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert sum(payload["summary"].values()) == len(_RESULTS)
