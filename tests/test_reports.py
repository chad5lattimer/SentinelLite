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


def _sample_results() -> list[ScanResult]:
    return [
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


def test_export_csv_has_exact_header_and_rows(tmp_path):
    destination = tmp_path / "results.csv"
    export_csv(_sample_results(), destination, timestamp="2026-09-09T12:00:00+00:00")

    with destination.open(newline="", encoding="utf-8") as file:
        rows = list(csv.reader(file))

    assert rows[0] == ["status", "path", "baseline_hash", "current_hash", "size", "timestamp"]
    assert len(rows) == 1 + len(_sample_results())

    by_path = {row[1]: row for row in rows[1:]}
    assert by_path["modified.txt"] == [
        "MODIFIED",
        "modified.txt",
        "aaa",
        "bbb",
        "10",
        "2026-09-09T12:00:00+00:00",
    ]
    # ERROR rows have no hashes/size, but must still appear with blank fields
    # rather than being silently dropped.
    assert by_path["locked.txt"][0] == "ERROR"
    assert by_path["locked.txt"][2] == ""
    assert by_path["locked.txt"][3] == ""
    assert by_path["locked.txt"][4] == ""


def test_export_csv_creates_parent_directories(tmp_path):
    destination = tmp_path / "nested" / "exports" / "results.csv"
    export_csv(_sample_results(), destination)
    assert destination.exists()


def test_export_json_matches_spec_shape(tmp_path):
    destination = tmp_path / "results.json"
    export_json(
        _sample_results(),
        destination,
        scan_id=42,
        timestamp="2026-09-09T12:00:00+00:00",
        root_directory="/monitored",
    )

    with destination.open(encoding="utf-8") as file:
        payload = json.load(file)  # raises if the file is not valid JSON

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
    assert len(payload["results"]) == 5

    paths = {entry["path"] for entry in payload["results"]}
    assert paths == {"modified.txt", "new.txt", "deleted.txt", "unchanged.txt", "locked.txt"}

    error_entry = next(entry for entry in payload["results"] if entry["path"] == "locked.txt")
    assert error_entry["status"] == "ERROR"
    assert error_entry["error_message"] == "Permission denied"


def test_export_json_handles_empty_results(tmp_path):
    destination = tmp_path / "empty.json"
    export_json(
        [], destination, scan_id=None, timestamp="2026-09-09T12:00:00+00:00", root_directory="/x"
    )

    with destination.open(encoding="utf-8") as file:
        payload = json.load(file)

    assert payload["scan_id"] is None
    assert payload["results"] == []
    assert payload["summary"] == {
        "modified": 0,
        "new": 0,
        "deleted": 0,
        "unchanged": 0,
        "errors": 0,
    }
