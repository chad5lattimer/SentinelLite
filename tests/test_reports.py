"""Tests for reports/exporter.py (PROJECT_SPEC.md section 15 / section 19).

Covers the "Reports" minimum test coverage from section 19:
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
    ScanResult(path="new.txt", status=ScanStatus.NEW, current_hash="ccc", size=5),
    ScanResult(path="deleted.txt", status=ScanStatus.DELETED, baseline_hash="ddd", size=7),
    ScanResult(
        path="unchanged.txt",
        status=ScanStatus.UNCHANGED,
        baseline_hash="eee",
        current_hash="eee",
        size=3,
    ),
    ScanResult(path="broken.txt", status=ScanStatus.ERROR, error_message="Permission denied"),
]


def test_export_csv_writes_header_and_all_rows(tmp_path):
    destination = tmp_path / "results.csv"
    export_csv(_RESULTS, destination, timestamp="Aug 26, 2026 12:45 AM")

    with destination.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))

    assert rows[0] == ["status", "path", "baseline_hash", "current_hash", "size", "timestamp"]
    assert len(rows) == 1 + len(_RESULTS)

    by_path = {row[1]: row for row in rows[1:]}
    assert by_path["modified.txt"] == [
        "MODIFIED", "modified.txt", "aaa", "bbb", "10", "Aug 26, 2026 12:45 AM",
    ]
    assert by_path["new.txt"][0] == "NEW"
    assert by_path["deleted.txt"][2] == "ddd"
    # Missing hash/size fields are written as empty cells, not "None".
    assert by_path["broken.txt"][2] == ""
    assert by_path["broken.txt"][4] == ""


def test_export_csv_returns_destination_path(tmp_path):
    destination = tmp_path / "out.csv"
    result = export_csv(_RESULTS, destination, timestamp="now")
    assert result == destination


def test_export_json_is_valid_and_matches_spec_shape(tmp_path):
    destination = tmp_path / "results.json"
    export_json(
        _RESULTS,
        destination,
        scan_id=42,
        timestamp="Aug 26, 2026 12:45 AM",
        root_directory="C:\\Users\\User\\Documents",
    )

    # Valid JSON syntax: json.loads must not raise.
    payload = json.loads(destination.read_text(encoding="utf-8"))

    assert payload["scan_id"] == 42
    assert payload["timestamp"] == "Aug 26, 2026 12:45 AM"
    assert payload["root_directory"] == "C:\\Users\\User\\Documents"
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

    broken = next(entry for entry in payload["results"] if entry["path"] == "broken.txt")
    assert broken["status"] == "ERROR"
    assert broken["error_message"] == "Permission denied"


def test_export_json_summary_counts_match_result_statuses(tmp_path):
    destination = tmp_path / "results.json"
    only_unchanged = [
        ScanResult(path="a.txt", status=ScanStatus.UNCHANGED, baseline_hash="x", current_hash="x", size=1),
        ScanResult(path="b.txt", status=ScanStatus.UNCHANGED, baseline_hash="y", current_hash="y", size=2),
    ]
    export_json(only_unchanged, destination, scan_id=1, timestamp="now", root_directory="C:\\Data")

    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["summary"]["unchanged"] == 2
    assert payload["summary"]["modified"] == 0
    assert payload["summary"]["new"] == 0
    assert payload["summary"]["deleted"] == 0
    assert payload["summary"]["errors"] == 0


def test_export_csv_and_json_handle_empty_results(tmp_path):
    csv_path = export_csv([], tmp_path / "empty.csv", timestamp="now")
    json_path = export_json([], tmp_path / "empty.json", scan_id=1, timestamp="now", root_directory="C:\\Data")

    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    assert rows == [["status", "path", "baseline_hash", "current_hash", "size", "timestamp"]]

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["results"] == []
    assert payload["summary"]["modified"] == 0
