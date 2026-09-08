"""Tests for core.baseline / storage.database / storage.repository
(PROJECT_SPEC.md section 19 - Baseline, section 28 - Run 3).

Covers the full acceptance-criteria loop from section 28:

    Create directory -> Create files -> Create baseline -> Modify
    filesystem -> Reload baseline

and that the reloaded baseline still reflects the original files, plus
missing-baseline and corrupted-baseline handling.
"""

from __future__ import annotations

import sqlite3

import pytest

from core.baseline import (
    Baseline,
    BaselineNotFoundError,
    create_baseline,
    find_baseline_for_directory,
    load_baseline,
    save_baseline,
)
from core.models import FileRecord
from storage.database import DatabaseCorruptedError, connect


def _write(path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_create_baseline_captures_files_in_memory(tmp_path):
    _write(tmp_path / "a.txt", b"one")
    _write(tmp_path / "Documents" / "b.txt", b"two")

    baseline, errors = create_baseline(tmp_path)

    assert errors == []
    assert baseline.baseline_id is None  # not yet saved
    assert baseline.file_count == 2
    assert {record.path for record in baseline.files} == {"a.txt", "Documents/b.txt"}
    assert baseline.root_directory == str(tmp_path)
    assert baseline.created_at  # non-empty ISO timestamp
    assert baseline.application_version


def test_save_and_load_baseline_round_trip(tmp_path):
    _write(tmp_path / "a.txt", b"one")
    _write(tmp_path / "b.txt", b"two")
    db_path = tmp_path / "sentinellite.db"

    baseline, _errors = create_baseline(tmp_path)

    with connect(db_path) as conn:
        saved = save_baseline(conn, baseline)
        assert saved.baseline_id is not None

        loaded = load_baseline(conn)

    assert loaded.baseline_id == saved.baseline_id
    assert loaded.root_directory == baseline.root_directory
    assert loaded.created_at == baseline.created_at
    assert loaded.application_version == baseline.application_version
    key = lambda record: record.path
    assert sorted(loaded.files, key=key) == sorted(baseline.files, key=key)


def test_baseline_survives_filesystem_modification(tmp_path):
    """The full Run 3 acceptance scenario: create -> modify -> reload."""
    _write(tmp_path / "unchanged.txt", b"same")
    _write(tmp_path / "will_change.txt", b"before")
    db_path = tmp_path / "sentinellite.db"

    baseline, _errors = create_baseline(tmp_path)
    with connect(db_path) as conn:
        saved = save_baseline(conn, baseline)
        baseline_id = saved.baseline_id

    # Modify the filesystem after saving.
    (tmp_path / "will_change.txt").write_bytes(b"after")
    (tmp_path / "new_file.txt").write_bytes(b"new")

    with connect(db_path) as conn:
        reloaded = load_baseline(conn, baseline_id)

    reloaded_by_path = {record.path: record for record in reloaded.files}
    assert reloaded_by_path.keys() == {"unchanged.txt", "will_change.txt"}
    # The stored hash reflects the file's content *at baseline time*, not
    # the modified content on disk now.
    assert reloaded_by_path["will_change.txt"].sha256 == baseline.files[
        [r.path for r in baseline.files].index("will_change.txt")
    ].sha256


def test_save_baseline_never_overwrites_prior_baseline(tmp_path):
    db_path = tmp_path / "sentinellite.db"
    _write(tmp_path / "a.txt", b"one")

    with connect(db_path) as conn:
        first, _ = create_baseline(tmp_path)
        first_saved = save_baseline(conn, first)

        second, _ = create_baseline(tmp_path)
        second_saved = save_baseline(conn, second)

        assert first_saved.baseline_id != second_saved.baseline_id

        # Both baselines remain individually loadable.
        assert load_baseline(conn, first_saved.baseline_id).baseline_id == first_saved.baseline_id
        assert load_baseline(conn, second_saved.baseline_id).baseline_id == second_saved.baseline_id
        # The latest one loads by default.
        assert load_baseline(conn).baseline_id == second_saved.baseline_id


def test_load_baseline_missing_raises(tmp_path):
    db_path = tmp_path / "sentinellite.db"

    with connect(db_path) as conn:
        with pytest.raises(BaselineNotFoundError):
            load_baseline(conn)


def test_load_baseline_unknown_id_raises(tmp_path):
    db_path = tmp_path / "sentinellite.db"
    _write(tmp_path / "a.txt", b"one")

    with connect(db_path) as conn:
        baseline, _ = create_baseline(tmp_path)
        save_baseline(conn, baseline)

        with pytest.raises(BaselineNotFoundError):
            load_baseline(conn, baseline_id=9999)


def test_corrupted_database_file_is_handled(tmp_path):
    db_path = tmp_path / "sentinellite.db"
    db_path.write_bytes(b"not a real sqlite database file")

    with pytest.raises(DatabaseCorruptedError):
        with connect(db_path):
            pass


def test_create_baseline_excludes_unreadable_files(tmp_path):
    import os
    import stat

    if os.name == "nt" or hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("Permission bits are not enforced for root or on Windows.")

    _write(tmp_path / "readable.txt", b"ok")
    blocked = tmp_path / "blocked.txt"
    _write(blocked, b"secret")
    blocked.chmod(0)

    try:
        baseline, errors = create_baseline(tmp_path)
    finally:
        blocked.chmod(stat.S_IRUSR | stat.S_IWUSR)

    assert {record.path for record in baseline.files} == {"readable.txt"}
    assert {error.path for error in errors} == {"blocked.txt"}


def test_find_baseline_for_directory_matches_per_folder(tmp_path):
    """GUI folder-switching (PROJECT_SPEC.md section 24) needs each
    monitored folder to find its own most recent baseline, not just the
    single most recent baseline overall."""
    dir_a = tmp_path / "A"
    dir_a.mkdir()
    _write(dir_a / "a.txt", b"one")
    dir_b = tmp_path / "B"
    dir_b.mkdir()
    _write(dir_b / "b.txt", b"two")
    db_path = tmp_path / "sentinellite.db"

    with connect(db_path) as conn:
        baseline_a, _ = create_baseline(dir_a)
        saved_a = save_baseline(conn, baseline_a)

        baseline_b, _ = create_baseline(dir_b)
        saved_b = save_baseline(conn, baseline_b)

        # dir_b's baseline is the most recent overall, but dir_a must still
        # resolve to its own baseline, not dir_b's.
        found_a = find_baseline_for_directory(conn, dir_a)
        assert found_a is not None
        assert found_a.baseline_id == saved_a.baseline_id

        found_b = find_baseline_for_directory(conn, dir_b)
        assert found_b is not None
        assert found_b.baseline_id == saved_b.baseline_id

        assert find_baseline_for_directory(conn, tmp_path / "NoBaselineHere") is None


def test_baseline_file_count_property():
    baseline = Baseline(
        root_directory="/tmp/x",
        created_at="2026-01-01T00:00:00+00:00",
        application_version="0.1.0",
        files=(
            FileRecord(path="a.txt", sha256="a" * 64, size=1, modified_time=0.0),
            FileRecord(path="b.txt", sha256="b" * 64, size=2, modified_time=0.0),
        ),
    )
    assert baseline.file_count == 2
