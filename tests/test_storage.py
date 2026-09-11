"""Direct unit tests for storage.database and storage.repository
(PROJECT_SPEC.md section 5 - Architecture, section 14 - Storage,
section 19 - Testing Requirements).

``tests/test_baseline.py`` and ``tests/test_scanner.py`` already exercise
this storage layer end-to-end through ``core.baseline`` / ``core.scanner``.
This file instead unit-tests ``storage.database`` and ``storage.repository``
directly and in isolation, per section 35's "testable independently"
requirement, covering repository behaviors (multi-baseline/multi-scan
lookups, filtering, ordering) that the higher-level tests do not exercise
directly.
"""

from __future__ import annotations

import sqlite3

import pytest

from core.models import FileRecord, ScanStatus
from core.scanner import ScanResult
from storage.database import DatabaseCorruptedError, connect, get_connection, initialize_database
from storage.repository import (
    get_baseline_files,
    get_baseline_metadata,
    get_latest_baseline_id,
    get_latest_baseline_id_for_directory,
    get_scan_results,
    insert_baseline,
    insert_scan,
    list_scans,
)


def _files() -> list[FileRecord]:
    return [
        FileRecord(path="a.txt", sha256="hash-a", size=1, modified_time=1.0),
        FileRecord(path="Documents/b.txt", sha256="hash-b", size=2, modified_time=2.0),
    ]


# --- storage.database -------------------------------------------------


def test_get_connection_creates_expected_schema(tmp_path):
    db_path = tmp_path / "sentinellite.db"

    connection = get_connection(db_path)
    try:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    finally:
        connection.close()

    assert {"baselines", "baseline_files", "scans", "scan_results"} <= tables


def test_connect_context_manager_closes_connection(tmp_path):
    db_path = tmp_path / "sentinellite.db"

    with connect(db_path) as connection:
        connection.execute("SELECT 1")

    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


def test_initialize_database_raises_on_corrupted_file(tmp_path):
    db_path = tmp_path / "corrupt.db"
    db_path.write_bytes(b"not a sqlite database")

    connection = sqlite3.connect(db_path)
    try:
        with pytest.raises(DatabaseCorruptedError):
            initialize_database(connection)
    finally:
        connection.close()


def test_get_connection_raises_and_closes_on_corrupted_file(tmp_path):
    db_path = tmp_path / "corrupt.db"
    db_path.write_bytes(b"not a sqlite database")

    with pytest.raises(DatabaseCorruptedError):
        get_connection(db_path)


# --- storage.repository: baselines -------------------------------------


def test_get_latest_baseline_id_is_none_when_empty(tmp_path):
    with connect(tmp_path / "sentinellite.db") as connection:
        assert get_latest_baseline_id(connection) is None
        assert get_latest_baseline_id_for_directory(connection, "/anywhere") is None


def test_insert_and_read_back_baseline(tmp_path):
    with connect(tmp_path / "sentinellite.db") as connection:
        baseline_id = insert_baseline(
            connection,
            created_at="2026-01-01T00:00:00",
            root_directory="/monitored",
            application_version="0.1.0",
            files=_files(),
        )

        metadata = get_baseline_metadata(connection, baseline_id)
        files = get_baseline_files(connection, baseline_id)

        assert metadata.baseline_id == baseline_id
        assert metadata.root_directory == "/monitored"
        assert metadata.application_version == "0.1.0"
        assert [record.path for record in files] == ["a.txt", "Documents/b.txt"]


def test_get_baseline_metadata_unknown_id_returns_none(tmp_path):
    with connect(tmp_path / "sentinellite.db") as connection:
        assert get_baseline_metadata(connection, 999) is None


def test_get_latest_baseline_id_for_directory_is_per_directory(tmp_path):
    with connect(tmp_path / "sentinellite.db") as connection:
        first = insert_baseline(
            connection,
            created_at="2026-01-01T00:00:00",
            root_directory="/one",
            application_version="0.1.0",
            files=_files(),
        )
        second = insert_baseline(
            connection,
            created_at="2026-01-02T00:00:00",
            root_directory="/two",
            application_version="0.1.0",
            files=_files(),
        )
        # A second, later baseline for "/one" should become its latest.
        third = insert_baseline(
            connection,
            created_at="2026-01-03T00:00:00",
            root_directory="/one",
            application_version="0.1.0",
            files=_files(),
        )

        assert get_latest_baseline_id_for_directory(connection, "/one") == third
        assert get_latest_baseline_id_for_directory(connection, "/two") == second
        assert get_latest_baseline_id(connection) == third
        assert first != third


# --- storage.repository: scans ------------------------------------------


def _scan_results() -> list[ScanResult]:
    return [
        ScanResult(path="a.txt", status=ScanStatus.UNCHANGED, baseline_hash="h", current_hash="h", size=1),
        ScanResult(path="new.txt", status=ScanStatus.NEW, current_hash="h2", size=2),
    ]


def test_insert_and_read_back_scan(tmp_path):
    with connect(tmp_path / "sentinellite.db") as connection:
        baseline_id = insert_baseline(
            connection,
            created_at="2026-01-01T00:00:00",
            root_directory="/monitored",
            application_version="0.1.0",
            files=_files(),
        )

        scan_id = insert_scan(
            connection,
            baseline_id=baseline_id,
            started_at="2026-01-02T00:00:00",
            completed_at="2026-01-02T00:00:01",
            modified_count=0,
            new_count=1,
            deleted_count=0,
            unchanged_count=1,
            error_count=0,
            results=_scan_results(),
        )

        results = get_scan_results(connection, scan_id)

        assert [result.path for result in results] == ["a.txt", "new.txt"]
        assert results[1].status is ScanStatus.NEW


def test_list_scans_orders_most_recent_first_and_filters_by_baseline(tmp_path):
    with connect(tmp_path / "sentinellite.db") as connection:
        baseline_one = insert_baseline(
            connection,
            created_at="2026-01-01T00:00:00",
            root_directory="/one",
            application_version="0.1.0",
            files=_files(),
        )
        baseline_two = insert_baseline(
            connection,
            created_at="2026-01-01T00:00:00",
            root_directory="/two",
            application_version="0.1.0",
            files=_files(),
        )

        scan_one = insert_scan(
            connection,
            baseline_id=baseline_one,
            started_at="2026-01-02T00:00:00",
            completed_at="2026-01-02T00:00:01",
            modified_count=0,
            new_count=0,
            deleted_count=0,
            unchanged_count=2,
            error_count=0,
            results=[],
        )
        scan_two = insert_scan(
            connection,
            baseline_id=baseline_two,
            started_at="2026-01-03T00:00:00",
            completed_at="2026-01-03T00:00:01",
            modified_count=1,
            new_count=0,
            deleted_count=0,
            unchanged_count=1,
            error_count=0,
            results=[],
        )

        all_scans = list_scans(connection)
        assert [scan.scan_id for scan in all_scans] == [scan_two, scan_one]

        only_baseline_one = list_scans(connection, baseline_id=baseline_one)
        assert [scan.scan_id for scan in only_baseline_one] == [scan_one]
