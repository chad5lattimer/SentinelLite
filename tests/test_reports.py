"""Tests for reports.exporter (PROJECT_SPEC.md section 15, section 19 - Reports).

Covers:
    - CSV generation with the exact column order from section 15.1.
    - JSON generation with the exact shape from section 15.2.
    - Correct summary counts.
    - Correct file paths.
    - Valid JSON syntax.

These tests operate purely on ``core.scanner.ScanResult`` objects -- no
GUI, filesystem scan, or database is involved (section 5's GUI/core/
storage separation extends naturally to reports).
"""

from __future__ import annotations

import csv
import json

from core.models import ScanStatus
from core.scanner import ScanResult
from reports.exporter import CSV_FIELDNAMES, default_export_filename, export_csv, export_json

_RESULTS = [
    ScanResult(
        path="modified.txt",
        status=ScanStatus.MODIFIED,
        baseline_hash="a" * 64,
        current_hash="b" * 64,
        size=10,
    ),
    ScanResult(
        path="new.txt",
        status=ScanStatus.NEW,
        baseline_hash=None,
        current_hash="c" * 64,
        size=5,
    ),
    ScanResult(
        path="deleted.txt",
        status=ScanStatus.DELETED,
        baseline_hash="d" * 64,
        current_hash=None,
        size=3,
    ),
    ScanResult(
        path="unchanged.txt",
        status=ScanStatus.UNCHANGED,
        baseline_hash="e" * 64,
        current_hash="e" * 64,
        size=7,
    ),
    ScanResult(
        path="locked.txt",
        status=ScanStatus.ERROR,
        baseline_hash="f" * 64,
        current_hash=None,
        size=None,
        error_message="Permission denied",
    ),
]


def test_default_export_filename_is_filesystem_safe():
    name = default_export_filename(scan_id=12, timestamp="2026-09-08T12:15:00+00:00", extension="csv")
    assert name == "sentinellite_scan_12_2026-09-08T121500Z.csv"
    assert ":" not in name


def test_export_csv_writes_header_and_exact_column_order(tmp_path):
    destination = tmp_path / "export.csv"
    result = export_csv(_RESULTS, destination, timestamp="2026-09-08T12:15:00+00:00")

    assert result == destination
    with destination.open(newline="", encoding="utf-8") as file:
        reader = csv.reader(file)
        header = next(reader)

    assert header == list(CSV_FIELDNAMES)
    assert header == ["status", "path", "baseline_hash", "current_hash", "size", "timestamp"]


def test_export_csv_contains_correct_paths_and_statuses(tmp_path):
    destination = tmp_path / "export.csv"
    export_csv(_RESULTS, destination, timestamp="2026-09-08T12:15:00+00:00")

    with destination.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))

    by_path = {row["path"]: row for row in rows}
    assert len(rows) == len(_RESULTS)
    assert by_path["modified.txt"]["status"] == "MODIFIED"
    assert by_path["modified.txt"]["baseline_hash"] == "a" * 64
    assert by_path["modified.txt"]["current_hash"] == "b" * 64
    assert by_path["new.txt"]["baseline_hash"] == ""  # None -> empty, not "None"
    assert by_path["locked.txt"]["status"] == "ERROR"
    assert all(row["timestamp"] == "2026-09-08T12:15:00+00:00" for row in rows)


def test_export_csv_creates_missing_parent_directory(tmp_path):
    destination = tmp_path / "exports" / "nested" / "export.csv"
    export_csv(_RESULTS, destination)
    assert destination.exists()


def test_export_json_is_valid_json_with_expected_shape(tmp_path):
    destination = tmp_path / "export.json"
    export_json(
        _RESULTS,
        destination,
        scan_id=42,
        timestamp="2026-09-08T12:15:00+00:00",
        root_directory="/monitored",
    )

    with destination.open(encoding="utf-8") as file:
        payload = json.load(file)  # raises if not valid JSON

    assert payload["scan_id"] == 42
    assert payload["timestamp"] == "2026-09-08T12:15:00+00:00"
    assert payload["root_directory"] == "/monitored"
    assert payload["summary"] == {
        "modified": 1,
        "new": 1,
        "deleted": 1,
        "unchanged": 1,
        "errors": 1,
    }
    assert len(payload["results"]) == len(_RESULTS)


def test_export_json_results_preserve_paths_and_fields(tmp_path):
    destination = tmp_path / "export.json"
    export_json(
        _RESULTS,
        destination,
        scan_id=1,
        timestamp="2026-09-08T12:15:00+00:00",
        root_directory="/monitored",
    )

    payload = json.loads(destination.read_text(encoding="utf-8"))
    by_path = {row["path"]: row for row in payload["results"]}

    assert by_path["modified.txt"]["status"] == "MODIFIED"
    assert by_path["modified.txt"]["baseline_hash"] == "a" * 64
    assert by_path["modified.txt"]["current_hash"] == "b" * 64
    assert by_path["new.txt"]["baseline_hash"] is None
    assert by_path["locked.txt"]["status"] == "ERROR"
    assert by_path["locked.txt"]["error_message"] == "Permission denied"


def test_export_json_creates_missing_parent_directory(tmp_path):
    destination = tmp_path / "exports" / "nested" / "export.json"
    export_json(
        _RESULTS, destination, scan_id=1, timestamp="2026-09-08T12:15:00+00:00", root_directory="/monitored"
    )
    assert destination.exists()


def test_export_empty_results_still_produces_valid_files(tmp_path):
    csv_destination = tmp_path / "empty.csv"
    json_destination = tmp_path / "empty.json"

    export_csv([], csv_destination, timestamp="2026-09-08T12:15:00+00:00")
    export_json(
        [], json_destination, scan_id=1, timestamp="2026-09-08T12:15:00+00:00", root_directory="/monitored"
    )

    with csv_destination.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    assert rows == []

    payload = json.loads(json_destination.read_text(encoding="utf-8"))
    assert payload["summary"] == {"modified": 0, "new": 0, "deleted": 0, "unchanged": 0, "errors": 0}
    assert payload["results"] == []
