"""Tests for core.baseline and storage.repository (PROJECT_SPEC.md
section 28 / Run 3).

Covers baseline creation, save/load round-tripping through SQLite, a
missing baseline, and a corrupted baseline database -- all without
crashing the application (PROJECT_SPEC.md section 19).
"""

from __future__ import annotations

import sqlite3

import pytest

from core.baseline import BaselineError, create_baseline, validate_baseline
from core.models import Baseline, FileRecord
from storage.repository import BaselineRepository


def _write(path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_create_baseline_hashes_every_file(tmp_path):
    _write(tmp_path / "a.txt", b"one")
    _write(tmp_path / "Documents" / "b.txt", b"two")

    baseline, errors = create_baseline(tmp_path)

    assert errors == []
    assert baseline.baseline_id is None
    assert baseline.root_directory == str(tmp_path)
    assert baseline.created_at
    assert baseline.application_version
    paths = {file.path for file in baseline.files}
    assert paths == {"a.txt", "Documents/b.txt"}


def test_baseline_can_be_saved_and_loaded(tmp_path):
    _write(tmp_path / "a.txt", b"content")
    baseline, _errors = create_baseline(tmp_path)

    repo = BaselineRepository(db_path=tmp_path / "sentinellite.db")
    saved = repo.save_baseline(baseline)

    assert saved.baseline_id is not None

    loaded = repo.load_baseline(saved.baseline_id)

    assert loaded is not None
    assert loaded.baseline_id == saved.baseline_id
    assert loaded.root_directory == baseline.root_directory
    assert loaded.created_at == baseline.created_at
    assert loaded.application_version == baseline.application_version
    assert sorted(loaded.files, key=lambda f: f.path) == sorted(baseline.files, key=lambda f: f.path)


def test_load_latest_baseline_returns_most_recent(tmp_path):
    monitored = tmp_path / "monitored"
    _write(monitored / "a.txt", b"one")
    first, _ = create_baseline(monitored)

    repo = BaselineRepository(db_path=tmp_path / "sentinellite.db")
    repo.save_baseline(first)

    _write(monitored / "b.txt", b"two")
    second, _ = create_baseline(monitored)
    saved_second = repo.save_baseline(second)

    latest = repo.load_latest_baseline()

    assert latest is not None
    assert latest.baseline_id == saved_second.baseline_id
    assert {f.path for f in latest.files} == {"a.txt", "b.txt"}


def test_baseline_reload_is_unaffected_by_later_filesystem_changes(tmp_path):
    """PROJECT_SPEC.md section 28 acceptance criteria: create directory,
    create files, create baseline, modify filesystem, reload baseline --
    the reloaded baseline must remain unchanged."""
    monitored = tmp_path / "monitored"
    _write(monitored / "unchanged.txt", b"same")
    _write(monitored / "will_change.txt", b"original")

    baseline, _errors = create_baseline(monitored)
    repo = BaselineRepository(db_path=tmp_path / "sentinellite.db")
    saved = repo.save_baseline(baseline)
    original_files = {f.path: f for f in saved.files}

    # Modify the filesystem after the baseline has been saved.
    _write(monitored / "will_change.txt", b"modified content")
    _write(monitored / "new_file.txt", b"new")
    (monitored / "unchanged.txt").unlink()

    reloaded = repo.load_baseline(saved.baseline_id)

    assert reloaded is not None
    reloaded_files = {f.path: f for f in reloaded.files}
    assert reloaded_files == original_files


def test_missing_baseline_is_handled(tmp_path):
    repo = BaselineRepository(db_path=tmp_path / "sentinellite.db")

    assert repo.has_baseline() is False
    assert repo.load_latest_baseline() is None
    assert repo.load_baseline(1) is None


def test_corrupted_baseline_database_is_handled(tmp_path):
    db_path = tmp_path / "sentinellite.db"
    db_path.write_bytes(b"this is not a valid sqlite database")

    repo = BaselineRepository(db_path=db_path)

    with pytest.raises(BaselineError):
        repo.load_latest_baseline()


def test_corrupted_baseline_row_is_handled(tmp_path):
    """A baseline row with an invalid hash (e.g. truncated by disk
    corruption) must be reported as a BaselineError, not loaded as-is."""
    _write(tmp_path / "a.txt", b"content")
    baseline, _errors = create_baseline(tmp_path)
    repo = BaselineRepository(db_path=tmp_path / "sentinellite.db")
    saved = repo.save_baseline(baseline)

    connection = sqlite3.connect(repo._db_path)
    connection.execute("UPDATE baseline_files SET sha256 = 'short' WHERE baseline_id = ?", (saved.baseline_id,))
    connection.commit()
    connection.close()

    with pytest.raises(BaselineError):
        repo.load_baseline(saved.baseline_id)


def test_save_baseline_rejects_invalid_baseline(tmp_path):
    bad_baseline = Baseline(
        baseline_id=None,
        created_at="",
        root_directory=str(tmp_path),
        application_version="0.1.0",
        files=(),
    )
    repo = BaselineRepository(db_path=tmp_path / "sentinellite.db")

    with pytest.raises(BaselineError):
        repo.save_baseline(bad_baseline)


def test_validate_baseline_rejects_duplicate_paths(tmp_path):
    file_record = FileRecord(path="a.txt", sha256="a" * 64, size=1, modified_time=0.0)
    baseline = Baseline(
        baseline_id=None,
        created_at="2026-01-01T00:00:00+00:00",
        root_directory=str(tmp_path),
        application_version="0.1.0",
        files=(file_record, file_record),
    )

    with pytest.raises(BaselineError):
        validate_baseline(baseline)


def test_validate_baseline_accepts_well_formed_baseline(tmp_path):
    file_record = FileRecord(path="a.txt", sha256="a" * 64, size=1, modified_time=0.0)
    baseline = Baseline(
        baseline_id=None,
        created_at="2026-01-01T00:00:00+00:00",
        root_directory=str(tmp_path),
        application_version="0.1.0",
        files=(file_record,),
    )

    validate_baseline(baseline)  # Should not raise.
