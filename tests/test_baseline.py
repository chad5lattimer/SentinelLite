"""Tests for core.baseline and storage.repository (PROJECT_SPEC.md section 19 - Baseline).

Covers:
    - Baseline can be created (from a real directory scan).
    - Baseline can be saved.
    - Baseline can be loaded.
    - Missing baseline is handled.
    - Corrupted baseline is handled.
    - The Run 3 acceptance scenario (section 28): create files, create
      baseline, modify the filesystem, reload the baseline, and the
      reloaded baseline is unaffected by the later filesystem changes.
"""

from __future__ import annotations

import sqlite3

import pytest

from core.baseline import Baseline, BaselineFile, BaselineValidationError, create_baseline, validate_baseline
from storage.repository import BaselineNotFoundError, BaselineRepository


def _write(path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


# ---------------------------------------------------------------------------
# Baseline creation
# ---------------------------------------------------------------------------


def test_create_baseline_hashes_every_file(tmp_path):
    monitored = tmp_path / "monitored"
    _write(monitored / "a.txt", b"one")
    _write(monitored / "Documents" / "b.txt", b"two")

    baseline, errors = create_baseline(monitored)

    assert errors == []
    assert baseline.baseline_id is None
    assert baseline.root_directory == str(monitored)
    assert baseline.file_count == 2
    paths = {entry.relative_path for entry in baseline.files}
    assert paths == {"a.txt", "Documents/b.txt"}


def test_create_baseline_records_application_version_and_timestamp(tmp_path):
    monitored = tmp_path / "monitored"
    _write(monitored / "a.txt", b"one")

    baseline, _errors = create_baseline(monitored)

    from config import APP_VERSION

    assert baseline.application_version == APP_VERSION
    assert baseline.created_at  # non-empty ISO timestamp


def test_create_baseline_on_missing_directory_raises(tmp_path):
    with pytest.raises(NotADirectoryError):
        create_baseline(tmp_path / "does_not_exist")


# ---------------------------------------------------------------------------
# Baseline validation
# ---------------------------------------------------------------------------


def test_validate_baseline_accepts_well_formed_baseline():
    baseline = Baseline(
        root_directory="/monitored",
        created_at="2026-09-06T00:00:00+00:00",
        application_version="0.1.0",
        files=(BaselineFile(relative_path="a.txt", sha256="a" * 64, size=3, modified_time=1.0),),
    )

    validate_baseline(baseline)  # does not raise


def test_validate_baseline_rejects_duplicate_paths():
    baseline = Baseline(
        root_directory="/monitored",
        created_at="2026-09-06T00:00:00+00:00",
        application_version="0.1.0",
        files=(
            BaselineFile(relative_path="a.txt", sha256="a" * 64, size=3, modified_time=1.0),
            BaselineFile(relative_path="a.txt", sha256="b" * 64, size=4, modified_time=2.0),
        ),
    )

    with pytest.raises(BaselineValidationError):
        validate_baseline(baseline)


def test_validate_baseline_rejects_invalid_hash_length():
    baseline = Baseline(
        root_directory="/monitored",
        created_at="2026-09-06T00:00:00+00:00",
        application_version="0.1.0",
        files=(BaselineFile(relative_path="a.txt", sha256="not-a-real-hash", size=3, modified_time=1.0),),
    )

    with pytest.raises(BaselineValidationError):
        validate_baseline(baseline)


def test_validate_baseline_rejects_missing_root_directory():
    baseline = Baseline(root_directory="", created_at="2026-09-06T00:00:00+00:00", application_version="0.1.0", files=())

    with pytest.raises(BaselineValidationError):
        validate_baseline(baseline)


# ---------------------------------------------------------------------------
# Save / load
# ---------------------------------------------------------------------------


def test_save_assigns_baseline_id(tmp_path):
    monitored = tmp_path / "monitored"
    _write(monitored / "a.txt", b"one")
    baseline, _errors = create_baseline(monitored)

    with BaselineRepository(tmp_path / "sentinellite.db") as repo:
        saved = repo.save(baseline)

    assert saved.baseline_id is not None


def test_load_latest_returns_saved_baseline(tmp_path):
    monitored = tmp_path / "monitored"
    _write(monitored / "a.txt", b"one")
    _write(monitored / "b.txt", b"two")
    baseline, _errors = create_baseline(monitored)

    db_path = tmp_path / "sentinellite.db"
    with BaselineRepository(db_path) as repo:
        saved = repo.save(baseline)

    with BaselineRepository(db_path) as repo:
        loaded = repo.load_latest()

    assert loaded.baseline_id == saved.baseline_id
    assert loaded.root_directory == baseline.root_directory
    assert loaded.application_version == baseline.application_version
    assert set(loaded.files) == set(baseline.files)


def test_load_by_id_returns_matching_baseline(tmp_path):
    monitored = tmp_path / "monitored"
    _write(monitored / "a.txt", b"one")
    baseline, _errors = create_baseline(monitored)

    db_path = tmp_path / "sentinellite.db"
    with BaselineRepository(db_path) as repo:
        saved = repo.save(baseline)
        loaded = repo.load(saved.baseline_id)

    assert loaded.baseline_id == saved.baseline_id


def test_has_baseline_reflects_saved_state(tmp_path):
    db_path = tmp_path / "sentinellite.db"
    with BaselineRepository(db_path) as repo:
        assert repo.has_baseline() is False

        monitored = tmp_path / "monitored"
        _write(monitored / "a.txt", b"one")
        baseline, _errors = create_baseline(monitored)
        repo.save(baseline)

        assert repo.has_baseline() is True


def test_saving_twice_keeps_the_newest_as_latest(tmp_path):
    monitored = tmp_path / "monitored"
    _write(monitored / "a.txt", b"one")
    db_path = tmp_path / "sentinellite.db"

    with BaselineRepository(db_path) as repo:
        first, _errors = create_baseline(monitored)
        repo.save(first)

        _write(monitored / "b.txt", b"two")
        second, _errors = create_baseline(monitored)
        second_saved = repo.save(second)

        latest = repo.load_latest()

    assert latest.baseline_id == second_saved.baseline_id
    assert latest.file_count == 2


# ---------------------------------------------------------------------------
# Missing / corrupted baseline handling
# ---------------------------------------------------------------------------


def test_load_latest_with_no_baseline_raises_not_found(tmp_path):
    with BaselineRepository(tmp_path / "sentinellite.db") as repo:
        with pytest.raises(BaselineNotFoundError):
            repo.load_latest()


def test_load_missing_id_raises_not_found(tmp_path):
    with BaselineRepository(tmp_path / "sentinellite.db") as repo:
        with pytest.raises(BaselineNotFoundError):
            repo.load(999)


def test_corrupted_database_file_raises_validation_error(tmp_path):
    db_path = tmp_path / "sentinellite.db"
    db_path.write_bytes(b"this is not a sqlite database")

    with BaselineRepository(db_path) as repo:
        with pytest.raises(BaselineValidationError):
            repo.load_latest()


def test_corrupted_baseline_row_raises_validation_error(tmp_path):
    monitored = tmp_path / "monitored"
    _write(monitored / "a.txt", b"one")
    baseline, _errors = create_baseline(monitored)

    db_path = tmp_path / "sentinellite.db"
    with BaselineRepository(db_path) as repo:
        repo.save(baseline)

    # Corrupt a persisted file entry directly at the storage layer, bypassing
    # the repository, to simulate a damaged database.
    conn = sqlite3.connect(db_path)
    with conn:
        conn.execute("UPDATE baseline_files SET sha256 = 'too-short'")
    conn.close()

    with BaselineRepository(db_path) as repo:
        with pytest.raises(BaselineValidationError):
            repo.load_latest()


# ---------------------------------------------------------------------------
# Run 3 acceptance scenario (PROJECT_SPEC.md section 28)
# ---------------------------------------------------------------------------


def test_reloaded_baseline_is_unaffected_by_later_filesystem_changes(tmp_path):
    monitored = tmp_path / "monitored"
    _write(monitored / "a.txt", b"original a")
    _write(monitored / "b.txt", b"original b")
    _write(monitored / "c.txt", b"original c")

    baseline, _errors = create_baseline(monitored)
    db_path = tmp_path / "sentinellite.db"
    with BaselineRepository(db_path) as repo:
        repo.save(baseline)

    # Modify the filesystem after the baseline was created.
    (monitored / "a.txt").write_bytes(b"changed a")
    (monitored / "b.txt").unlink()
    _write(monitored / "d.txt", b"new file")

    with BaselineRepository(db_path) as repo:
        reloaded = repo.load_latest()

    reloaded_paths = {entry.relative_path for entry in reloaded.files}
    assert reloaded_paths == {"a.txt", "b.txt", "c.txt"}

    original_a_hash = next(entry.sha256 for entry in baseline.files if entry.relative_path == "a.txt")
    reloaded_a_hash = next(entry.sha256 for entry in reloaded.files if entry.relative_path == "a.txt")
    assert reloaded_a_hash == original_a_hash
