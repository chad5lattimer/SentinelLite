"""Tests for reports/exporter.py (PROJECT_SPEC.md section 15 / Run 6).

Covers:
    - CSV generation (header, rows, correct file paths).
    - JSON generation (valid syntax, correct shape/summary counts).
    - Files/hashes that are ``None`` (NEW/DELETED results) round-trip as
      empty strings (CSV) / ``null`` (JSON) rather than crashing.
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
    ScanResult(
        path="new.txt",
        status=ScanStatus.NEW,
        baseline_hash=None,
        current_hash="ccc",
        size=5,
    ),
    ScanResult(
        path="deleted.txt",
        status=ScanStatus.DELETED,
        baseline_hash="ddd",
        current_hash=None,
        size=3,
    ),
    ScanResult(
        path="unchanged.txt",
        status=ScanStatus.UNCHANGED,
        baseline_hash="eee",
        current_hash="eee",
        size=7,
    ),
    ScanResult(
        path="broken.txt",
        status=ScanStatus.ERROR,
        baseline_hash="fff",
        current_hash=None,
        size=None,
        error_message="Permission denied",
    ),
]


def test_export_csv_writes_header_and_correct_rows(tmp_path):
    destination = tmp_path / "exports" / "scan.csv"

    result_path = export_csv(_RESULTS, destination, timestamp="2026-09-09T12:00:00+00:00")

    assert result_path == destination
    assert destination.exists()

    with destination.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))

    assert rows[0] == ["status", "path", "baseline_hash", "current_hash", "size", "timestamp"]
    assert len(rows) == 1 + len(_RESULTS)

    modified_row = rows[1]
    assert modified_row == [
        "MODIFIED", "modified.txt", "aaa", "bbb", "10", "2026-09-09T12:00:00+00:00",
    ]

    # NEW/DELETED results have a missing baseline_hash/current_hash -- these
    # must round-trip as empty strings, not the literal "None".
    new_row = rows[2]
    assert new_row[2] == ""  # baseline_hash
    deleted_row = rows[3]
    assert deleted_row[3] == ""  # current_hash


def test_export_csv_creates_parent_directories(tmp_path):
    destination = tmp_path / "does" / "not" / "exist" / "scan.csv"
    export_csv(_RESULTS, destination)
    assert destination.exists()


def test_export_json_produces_valid_syntax_and_correct_summary(tmp_path):
    destination = tmp_path / "scan.json"

    export_json(
        _RESULTS,
        destination,
        scan_id=42,
        timestamp="2026-09-09T12:00:00+00:00",
        root_directory="/monitored",
    )

    with destination.open(encoding="utf-8") as handle:
        payload = json.load(handle)  # raises if not valid JSON

    assert payload["scan_id"] == 42
    assert payload["timestamp"] == "2026-09-09T12:00:00+00:00"
    assert payload["root_directory"] == "/monitored"
    assert payload["summary"] == {
        "modified": 1,
        "new": 1,
        "deleted": 1,
        "unchanged": 1,
        "errors": 1,
    }
    assert len(payload["results"]) == len(_RESULTS)

    modified_entry = payload["results"][0]
    assert modified_entry == {
        "path": "modified.txt",
        "status": "MODIFIED",
        "baseline_hash": "aaa",
        "current_hash": "bbb",
        "size": 10,
        "error_message": None,
    }

    error_entry = payload["results"][4]
    assert error_entry["status"] == "ERROR"
    assert error_entry["error_message"] == "Permission denied"
    assert error_entry["size"] is None


def test_export_json_creates_parent_directories(tmp_path):
    destination = tmp_path / "does" / "not" / "exist" / "scan.json"
    export_json(_RESULTS, destination, scan_id=1, timestamp="", root_directory="/x")
    assert destination.exists()


def test_export_csv_and_json_handle_empty_results(tmp_path):
    csv_destination = tmp_path / "empty.csv"
    json_destination = tmp_path / "empty.json"

    export_csv([], csv_destination)
    export_json([], json_destination, scan_id=1, timestamp="", root_directory="/x")

    with csv_destination.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    assert rows == [["status", "path", "baseline_hash", "current_hash", "size", "timestamp"]]

    with json_destination.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    assert payload["results"] == []
    assert payload["summary"] == {"modified": 0, "new": 0, "deleted": 0, "unchanged": 0, "errors": 0}
