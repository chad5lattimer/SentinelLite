"""Tests for storage.database and storage.repository (PROJECT_SPEC.md
section 14 / Run 3).

Covers schema creation and the BaselineRepository's save/load/replace
behavior directly against SQLite, independent of core.baseline.
"""

from __future__ import annotations

import sqlite3

import pytest

from core.models import FileRecord
from storage.database import get_connection, initialize_schema
from storage.repository import (
    BaselineCorruptedError,
    BaselineNotFoundError,
    BaselineRepository,
)


@pytest.fixture
def connection(tmp_path):
    conn = get_connection(tmp_path / "sentinellite.db")
    yield conn
    conn.close()


def _make_baseline(root="C:/Monitored", files=None):
    from core.baseline import Baseline

    return Baseline(
        root_directory=root,
        files=files if files is not None else [FileRecord("a.txt", "hash-a", 3, 100.0)],
        created_at="2026-09-07T00:00:00+00:00",
        application_version="0.1.0",
    )


def test_get_connection_creates_expected_tables(connection):
    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"baselines", "baseline_files", "scans", "scan_results"} <= tables


def test_initialize_schema_is_idempotent(connection):
    # Calling again must not raise or duplicate anything.
    initialize_schema(connection)
    initialize_schema(connection)


def test_repository_save_and_load_round_trip(connection):
    repo = BaselineRepository(connection)
    baseline = _make_baseline(files=[
        FileRecord("a.txt", "hash-a", 3, 100.0),
        FileRecord("Documents/notes.txt", "hash-b", 10, 200.5),
    ])

    baseline_id = repo.save(baseline)
    loaded = repo.load_by_id(baseline_id)

    assert loaded.baseline_id == baseline_id
    assert loaded.root_directory == baseline.root_directory
    assert loaded.created_at == baseline.created_at
    assert loaded.application_version == baseline.application_version
    assert sorted(loaded.files, key=lambda f: f.path) == sorted(baseline.files, key=lambda f: f.path)


def test_repository_load_latest_for_directory(connection):
    repo = BaselineRepository(connection)
    baseline = _make_baseline(root="C:/Monitored")
    repo.save(baseline)

    loaded = repo.load_latest_for_directory("C:/Monitored")

    assert loaded.root_directory == "C:/Monitored"
    assert loaded.files == baseline.files


def test_repository_save_replaces_previous_baseline_for_same_directory(connection):
    repo = BaselineRepository(connection)
    repo.save(_make_baseline(root="C:/Monitored", files=[FileRecord("old.txt", "h1", 1, 1.0)]))
    new_id = repo.save(_make_baseline(root="C:/Monitored", files=[FileRecord("new.txt", "h2", 2, 2.0)]))

    loaded = repo.load_latest_for_directory("C:/Monitored")

    assert loaded.baseline_id == new_id
    assert [f.path for f in loaded.files] == ["new.txt"]
    # Only one baseline row should remain for this directory.
    remaining = connection.execute(
        "SELECT COUNT(*) AS n FROM baselines WHERE root_directory = ?", ("C:/Monitored",)
    ).fetchone()["n"]
    assert remaining == 1


def test_repository_load_missing_baseline_raises(connection):
    repo = BaselineRepository(connection)

    with pytest.raises(BaselineNotFoundError):
        repo.load_latest_for_directory("C:/DoesNotExist")

    with pytest.raises(BaselineNotFoundError):
        repo.load_by_id(9999)


def test_repository_load_corrupted_baseline_raises(connection):
    repo = BaselineRepository(connection)
    baseline_id = repo.save(_make_baseline())

    # Simulate a corrupted baseline_files row (unreadable/unexpected data)
    # by dropping a required column's table out from under the repository.
    connection.execute("DROP TABLE baseline_files")
    connection.commit()

    with pytest.raises(BaselineCorruptedError):
        repo.load_by_id(baseline_id)


def test_get_connection_rejects_non_database_file(tmp_path):
    bogus = tmp_path / "not_a_database.db"
    bogus.write_text("this is not a sqlite file, just text")

    with pytest.raises(sqlite3.DatabaseError):
        get_connection(bogus)
