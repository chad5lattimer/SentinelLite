"""Tests for reports.exporter (PROJECT_SPEC.md section 19 - Reports,
section 31 - Run 6).

Covers:
    - CSV generation.
    - JSON generation.
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
    ScanResult(
        path="new.txt",
        status=ScanStatus.NEW,
        baseline_hash=None,
        current_hash="ccc",
        size=20,
    ),
    ScanResult(
        path="deleted.txt",
        status=ScanStatus.DELETED,
        baseline_hash="ddd",
        current_hash=None,
        size=30,
    ),
    ScanResult(
        path="unchanged.txt",
        status=ScanStatus.UNCHANGED,
        baseline_hash="eee",
        current_hash="eee",
        size=40,
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

_TIMESTAMP = "2026-09-09T12:00:00+00:00"


def test_export_csv_writes_header_and_rows(tmp_path):
    destination = tmp_path / "scan.csv"
    result_path = export_csv(_RESULTS, destination, timestamp=_TIMESTAMP)

    assert result_path == destination
    assert destination.exists()

    with destination.open(newline="", encoding="utf-8") as file:
        rows = list(csv.reader(file))

    assert rows[0] == ["status", "path", "baseline_hash", "current_hash", "size", "timestamp"]
    assert len(rows) == 1 + len(_RESULTS)

    # Correct file paths are present in the expected order.
    exported_paths = [row[1] for row in rows[1:]]
    assert exported_paths == [result.path for result in _RESULTS]

    modified_row = rows[1]
    assert modified_row == ["MODIFIED", "modified.txt", "aaa", "bbb", "10", _TIMESTAMP]

    # Missing hash/size fields are exported as empty strings, not "None".
    error_row = rows[5]
    assert error_row == ["ERROR", "broken.txt", "fff", "", "", _TIMESTAMP]


def test_export_csv_creates_parent_directories(tmp_path):
    destination = tmp_path / "nested" / "exports" / "scan.csv"
    export_csv(_RESULTS, destination, timestamp=_TIMESTAMP)
    assert destination.exists()


def test_export_json_is_valid_and_matches_section_15_2_shape(tmp_path):
    destination = tmp_path / "scan.json"
    export_json(
        _RESULTS,
        destination,
        scan_id=1,
        timestamp=_TIMESTAMP,
        root_directory="C:\\Monitored",
    )

    # Valid JSON syntax.
    payload = json.loads(destination.read_text(encoding="utf-8"))

    assert payload["scan_id"] == 1
    assert payload["timestamp"] == _TIMESTAMP
    assert payload["root_directory"] == "C:\\Monitored"

    # Correct summary counts.
    assert payload["summary"] == {
        "modified": 1,
        "new": 1,
        "deleted": 1,
        "unchanged": 1,
        "errors": 1,
    }

    # Correct file paths, in order, each with its status.
    assert [entry["path"] for entry in payload["results"]] == [
        result.path for result in _RESULTS
    ]
    assert payload["results"][0]["status"] == "MODIFIED"
    assert payload["results"][4]["error_message"] == "Permission denied"


def test_export_json_creates_parent_directories(tmp_path):
    destination = tmp_path / "nested" / "exports" / "scan.json"
    export_json(
        _RESULTS, destination, scan_id=2, timestamp=_TIMESTAMP, root_directory="C:\\Monitored"
    )
    assert destination.exists()


def test_export_empty_results(tmp_path):
    """Exporting a scan with zero results should not error (e.g. an empty
    monitored directory)."""
    csv_destination = export_csv([], tmp_path / "empty.csv", timestamp=_TIMESTAMP)
    json_destination = export_json(
        [], tmp_path / "empty.json", scan_id=3, timestamp=_TIMESTAMP, root_directory="C:\\Empty"
    )

    with csv_destination.open(newline="", encoding="utf-8") as file:
        rows = list(csv.reader(file))
    assert rows == [["status", "path", "baseline_hash", "current_hash", "size", "timestamp"]]

    payload = json.loads(json_destination.read_text(encoding="utf-8"))
    assert payload["results"] == []
    assert payload["summary"] == {
        "modified": 0,
        "new": 0,
        "deleted": 0,
        "unchanged": 0,
        "errors": 0,
    }
