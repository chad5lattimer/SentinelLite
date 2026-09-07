"""Tests for core.baseline (PROJECT_SPEC.md section 19 - Baseline / Run 3).

Covers the acceptance scenario from PROJECT_SPEC.md section 28:

    Create directory -> Create files -> Create baseline -> Modify
    filesystem -> Reload baseline -> baseline remains unchanged.

as well as missing/corrupted baseline handling.
"""

from __future__ import annotations

import pytest

from core.baseline import Baseline, create_baseline, load_baseline
from storage.database import get_connection
from storage.repository import BaselineCorruptedError, BaselineNotFoundError, BaselineRepository


@pytest.fixture
def repository(tmp_path_factory):
    # The database must live outside the directory being monitored/scanned
    # in these tests, or scan_directory would pick up the .db file itself.
    db_dir = tmp_path_factory.mktemp("db")
    connection = get_connection(db_dir / "sentinellite.db")
    yield BaselineRepository(connection)
    connection.close()


def _write(path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_create_baseline_enumerates_and_saves_files(tmp_path, repository):
    _write(tmp_path / "file1.txt", b"one")
    _write(tmp_path / "Documents" / "notes.txt", b"two")

    baseline, errors = create_baseline(tmp_path, repository)

    assert errors == []
    assert isinstance(baseline, Baseline)
    assert baseline.baseline_id is not None
    assert baseline.root_directory == str(tmp_path)
    assert {f.path for f in baseline.files} == {"file1.txt", "Documents/notes.txt"}


def test_baseline_is_reloadable_and_unchanged_after_filesystem_modification(tmp_path, repository):
    _write(tmp_path / "A.txt", b"original")
    _write(tmp_path / "B.txt", b"stays deleted later")
    _write(tmp_path / "C.txt", b"unchanged")

    baseline, errors = create_baseline(tmp_path, repository)
    assert errors == []

    # Modify the filesystem after the baseline was taken.
    (tmp_path / "A.txt").write_bytes(b"changed contents")
    (tmp_path / "B.txt").unlink()
    _write(tmp_path / "D.txt", b"a new file")

    reloaded = load_baseline(tmp_path, repository)

    # The reloaded baseline reflects the filesystem state at creation time,
    # not the current (modified) filesystem -- it is the trust reference
    # comparisons will be made against (PROJECT_SPEC.md section 17.2).
    assert reloaded.baseline_id == baseline.baseline_id
    assert sorted(reloaded.files, key=lambda f: f.path) == sorted(baseline.files, key=lambda f: f.path)
    reloaded_hashes = {f.path: f.sha256 for f in reloaded.files}
    assert reloaded_hashes == {f.path: f.sha256 for f in baseline.files}
    assert {"A.txt", "B.txt", "C.txt"} == set(reloaded_hashes)
    assert "D.txt" not in reloaded_hashes


def test_creating_a_new_baseline_replaces_the_old_one(tmp_path, repository):
    _write(tmp_path / "old.txt", b"v1")
    create_baseline(tmp_path, repository)

    (tmp_path / "old.txt").unlink()
    _write(tmp_path / "new.txt", b"v2")
    second_baseline, errors = create_baseline(tmp_path, repository)

    assert errors == []
    reloaded = load_baseline(tmp_path, repository)
    assert reloaded.baseline_id == second_baseline.baseline_id
    assert [f.path for f in reloaded.files] == ["new.txt"]


def test_load_baseline_missing_is_handled(tmp_path, repository):
    with pytest.raises(BaselineNotFoundError):
        load_baseline(tmp_path, repository)


def test_load_baseline_corrupted_is_handled(tmp_path, repository):
    _write(tmp_path / "file1.txt", b"one")
    create_baseline(tmp_path, repository)

    # Simulate database corruption discovered at load time.
    repository._connection.execute("DROP TABLE baseline_files")
    repository._connection.commit()

    with pytest.raises(BaselineCorruptedError):
        load_baseline(tmp_path, repository)


def test_create_baseline_continues_after_unreadable_file(tmp_path, repository, monkeypatch):
    _write(tmp_path / "good.txt", b"ok")
    _write(tmp_path / "bad.txt", b"unreadable")

    import core.filesystem as filesystem_module

    original_hash = filesystem_module.calculate_sha256

    def fake_hash(path, **kwargs):
        if path.name == "bad.txt":
            raise OSError("Permission denied")
        return original_hash(path, **kwargs)

    monkeypatch.setattr(filesystem_module, "calculate_sha256", fake_hash)

    baseline, errors = create_baseline(tmp_path, repository)

    assert [e.path for e in errors] == ["bad.txt"]
    assert {f.path for f in baseline.files} == {"good.txt"}
    # The baseline is still saved and loadable despite the partial error.
    reloaded = load_baseline(tmp_path, repository)
    assert {f.path for f in reloaded.files} == {"good.txt"}
