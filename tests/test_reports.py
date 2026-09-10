"""Tests for reports.exporter (PROJECT_SPEC.md section 19 - Reports,
section 31 - Run 6).

Per section 19's minimum coverage for reports:
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
from reports.exporter import export_to_csv, export_to_json

_RESULTS = [
    ScanResult(
        path="modified.txt",
        status=ScanStatus.MODIFIED,
        baseline_hash="aaa",
        current_hash="bbb",
        size=10,
    ),
    ScanResult(path="new.txt", status=ScanStatus.NEW, current_hash="ccc", size=5),
    ScanResult(path="deleted.txt", status=ScanStatus.DELETED, baseline_hash="ddd", size=7),
    ScanResult(
        path="unchanged.txt",
        status=ScanStatus.UNCHANGED,
        baseline_hash="eee",
        current_hash="eee",
        size=3,
    ),
    ScanResult(path="locked.txt", status=ScanStatus.ERROR, error_message="Permission denied"),
]


def test_export_to_csv_writes_header_and_rows(tmp_path):
    destination = tmp_path / "results.csv"

    returned = export_to_csv(_RESULTS, destination, timestamp="Sep 08, 2026 12:00 AM")

    assert returned == destination
    assert destination.exists()

    with destination.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))

    # Header exactly matches PROJECT_SPEC.md section 15.1.
    assert rows[0] == ["status", "path", "baseline_hash", "current_hash", "size", "timestamp"]
    assert len(rows) == 1 + len(_RESULTS)

    modified_row = rows[1]
    assert modified_row == ["MODIFIED", "modified.txt", "aaa", "bbb", "10", "Sep 08, 2026 12:00 AM"]

    # Missing hashes/size are written as empty fields, not "None".
    new_row = rows[2]
    assert new_row == ["NEW", "new.txt", "", "ccc", "5", "Sep 08, 2026 12:00 AM"]


def test_export_to_csv_creates_parent_directories(tmp_path):
    destination = tmp_path / "nested" / "dir" / "results.csv"
    export_to_csv(_RESULTS, destination)
    assert destination.exists()


def test_export_to_json_is_valid_and_matches_shape(tmp_path):
    destination = tmp_path / "results.json"

    export_to_json(
        _RESULTS,
        destination,
        scan_id=42,
        timestamp="Sep 08, 2026 12:00 AM",
        root_directory="/monitored",
    )

    # Valid JSON syntax.
    with destination.open(encoding="utf-8") as handle:
        payload = json.load(handle)

    # Shape matches PROJECT_SPEC.md section 15.2.
    assert payload["scan_id"] == 42
    assert payload["timestamp"] == "Sep 08, 2026 12:00 AM"
    assert payload["root_directory"] == "/monitored"

    # Correct summary counts.
    assert payload["summary"] == {
        "modified": 1,
        "new": 1,
        "deleted": 1,
        "unchanged": 1,
        "errors": 1,
    }

    # Correct file paths, one result per input record.
    assert len(payload["results"]) == len(_RESULTS)
    paths = {entry["path"] for entry in payload["results"]}
    assert paths == {"modified.txt", "new.txt", "deleted.txt", "unchanged.txt", "locked.txt"}

    error_entry = next(entry for entry in payload["results"] if entry["path"] == "locked.txt")
    assert error_entry["status"] == "ERROR"
    assert error_entry["error_message"] == "Permission denied"


def test_export_to_json_handles_empty_results(tmp_path):
    destination = tmp_path / "empty.json"
    export_to_json([], destination, scan_id=1, timestamp="", root_directory="/monitored")

    with destination.open(encoding="utf-8") as handle:
        payload = json.load(handle)

    assert payload["results"] == []
    assert payload["summary"] == {"modified": 0, "new": 0, "deleted": 0, "unchanged": 0, "errors": 0}


def test_export_to_json_creates_parent_directories(tmp_path):
    destination = tmp_path / "nested" / "dir" / "results.json"
    export_to_json(_RESULTS, destination, scan_id=1, timestamp="", root_directory="/monitored")
    assert destination.exists()
