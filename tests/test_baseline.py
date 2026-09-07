"""Tests for the baseline system (PROJECT_SPEC.md section 19 - Baseline).

Covers:
    - A baseline can be created (files enumerated, hashed, saved).
    - A baseline can be saved and reloaded, unaffected by later filesystem
      changes (the Run 3 acceptance-criteria flow in section 28).
    - A missing baseline is handled (no baseline yet / unknown id).
    - A corrupted baseline (unreadable database file) is handled.
    - Unreadable files are excluded from the baseline and reported
      separately as errors.
"""

from __future__ import annotations

import os
import stat

import pytest

from core.baseline import (
    BaselineLoadError,
    create_baseline,
    has_existing_baseline,
    load_baseline,
    load_latest_baseline,
    open_database,
)
from core.models import Baseline
from storage import database
from storage.repository import BaselineNotFoundError


@pytest.fixture()
def connection(tmp_path):
    conn = database.connect(tmp_path / "sentinellite.db")
    yield conn
    conn.close()


def _make_files(root):
    (root / "a.txt").write_bytes(b"alpha")
    (root / "sub").mkdir()
    (root / "sub" / "b.txt").write_bytes(b"beta")


def test_baseline_can_be_created(tmp_path, connection):
    monitored = tmp_path / "monitored"
    monitored.mkdir()
    _make_files(monitored)

    baseline, errors = create_baseline(monitored, connection)

    assert errors == []
    assert isinstance(baseline, Baseline)
    assert baseline.baseline_id is not None
    assert baseline.root_directory == str(monitored)
    assert {record.path for record in baseline.files} == {"a.txt", "sub/b.txt"}


def test_has_existing_baseline_reflects_state(tmp_path, connection):
    monitored = tmp_path / "monitored"
    monitored.mkdir()
    _make_files(monitored)

    assert has_existing_baseline(connection) is False

    create_baseline(monitored, connection)

    assert has_existing_baseline(connection) is True


def test_baseline_saved_and_reloaded_unaffected_by_later_changes(tmp_path, connection):
    """Section 28 acceptance flow: create dir -> create files -> create
    baseline -> modify filesystem -> reload baseline -> baseline unchanged.
    """
    monitored = tmp_path / "monitored"
    monitored.mkdir()
    _make_files(monitored)

    created, _ = create_baseline(monitored, connection)

    # Modify the filesystem after the baseline was taken.
    (monitored / "a.txt").write_bytes(b"tampered")
    (monitored / "new.txt").write_bytes(b"new file")
    (monitored / "sub" / "b.txt").unlink()

    reloaded = load_baseline(connection, created.baseline_id)

    assert reloaded == created
    assert {record.path for record in reloaded.files} == {"a.txt", "sub/b.txt"}
    original_hash = next(r.sha256 for r in reloaded.files if r.path == "a.txt")
    assert original_hash == next(r.sha256 for r in created.files if r.path == "a.txt")


def test_load_latest_baseline_returns_none_when_none_exists(connection):
    assert load_latest_baseline(connection) is None


def test_load_latest_baseline_returns_most_recent(tmp_path, connection):
    first_dir = tmp_path / "first"
    first_dir.mkdir()
    _make_files(first_dir)
    second_dir = tmp_path / "second"
    second_dir.mkdir()
    (second_dir / "only.txt").write_bytes(b"only file")

    create_baseline(first_dir, connection)
    second_baseline, _ = create_baseline(second_dir, connection)

    latest = load_latest_baseline(connection)

    assert latest.baseline_id == second_baseline.baseline_id
    assert latest.root_directory == str(second_dir)


def test_loading_unknown_baseline_id_raises_friendly_error(connection):
    with pytest.raises(BaselineLoadError):
        load_baseline(connection, 999)


def test_repository_raises_typed_error_for_unknown_id(connection):
    # storage.repository itself raises a distinct, lower-level exception;
    # core.baseline wraps it into BaselineLoadError above.
    from storage.repository import load_baseline as repo_load_baseline

    with pytest.raises(BaselineNotFoundError):
        repo_load_baseline(connection, 999)


def test_corrupted_database_file_is_handled(tmp_path):
    db_path = tmp_path / "corrupt.db"
    db_path.write_bytes(b"this is not a sqlite database")

    with pytest.raises(BaselineLoadError):
        open_database(db_path)


def test_unreadable_file_excluded_from_baseline_and_reported_as_error(tmp_path, connection):
    if os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0):
        pytest.skip("Permission bits are not enforced for root or on Windows.")

    monitored = tmp_path / "monitored"
    monitored.mkdir()
    _make_files(monitored)
    secret = monitored / "secret.txt"
    secret.write_bytes(b"top secret")
    secret.chmod(0)

    try:
        baseline, errors = create_baseline(monitored, connection)
    finally:
        secret.chmod(stat.S_IRUSR | stat.S_IWUSR)

    assert "secret.txt" not in {record.path for record in baseline.files}
    assert any(error.path == "secret.txt" for error in errors)
