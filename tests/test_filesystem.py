"""Tests for core.filesystem, per PROJECT_SPEC.md sections 8 and 19."""

from __future__ import annotations

import pytest

import core.filesystem as fs


def test_iter_files_recurses_and_sorts(tmp_path):
    (tmp_path / "b.txt").write_text("b")
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "Documents").mkdir()
    (tmp_path / "Documents" / "notes.txt").write_text("notes")

    files = list(fs.iter_files(tmp_path))

    # Filenames are sorted within each directory; directories are visited
    # top-down (the top-level files come before the nested ones).
    assert files == [
        tmp_path / "a.txt",
        tmp_path / "b.txt",
        tmp_path / "Documents" / "notes.txt",
    ]


def test_iter_files_skips_symlinked_file_by_default(tmp_path):
    target = tmp_path / "target.txt"
    target.write_text("secret")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are not supported in this environment.")

    files = list(fs.iter_files(tmp_path))

    assert target in files
    assert link not in files


def test_iter_files_does_not_descend_into_symlinked_directory(tmp_path):
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    (real_dir / "inside.txt").write_text("inside")

    link_dir = tmp_path / "link_dir"
    try:
        link_dir.symlink_to(real_dir, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are not supported in this environment.")

    files = list(fs.iter_files(tmp_path))

    assert real_dir / "inside.txt" in files
    assert all(link_dir not in path.parents for path in files)


def test_iter_files_continues_after_directory_permission_error(tmp_path, monkeypatch):
    (tmp_path / "reachable.txt").write_text("ok")

    def fake_walk(top, onerror=None, followlinks=False):
        onerror(PermissionError("Permission denied: /protected"))
        yield (str(tmp_path), [], ["reachable.txt"])

    monkeypatch.setattr(fs.os, "walk", fake_walk)

    files = list(fs.iter_files(tmp_path))

    assert files == [tmp_path / "reachable.txt"]


def test_collect_file_records_builds_expected_records(tmp_path):
    (tmp_path / "file1.txt").write_bytes(b"hello")
    (tmp_path / "Config").mkdir()
    (tmp_path / "Config" / "settings.ini").write_bytes(b"[section]")

    records, errors = fs.collect_file_records(tmp_path)

    assert errors == []
    paths = {record.path for record in records}
    assert paths == {"file1.txt", "Config/settings.ini"}

    file1 = next(r for r in records if r.path == "file1.txt")
    assert file1.size == 5
    assert len(file1.sha256) == 64  # hex-encoded SHA-256 digest


def test_collect_file_records_reports_errors_and_continues(tmp_path, monkeypatch):
    (tmp_path / "good.txt").write_text("hello")
    (tmp_path / "bad.txt").write_text("world")

    original_hash = fs.calculate_sha256

    def flaky_hash(path, *args, **kwargs):
        if path.name == "bad.txt":
            raise OSError("Permission denied")
        return original_hash(path, *args, **kwargs)

    monkeypatch.setattr(fs, "calculate_sha256", flaky_hash)

    records, errors = fs.collect_file_records(tmp_path)

    assert [record.path for record in records] == ["good.txt"]
    assert [error.path for error in errors] == ["bad.txt"]
    assert "Permission denied" in errors[0].error


def test_collect_file_records_uses_relative_posix_paths(tmp_path):
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    (nested / "c.txt").write_text("data")

    records, errors = fs.collect_file_records(tmp_path)

    assert errors == []
    assert records[0].path == "a/b/c.txt"
