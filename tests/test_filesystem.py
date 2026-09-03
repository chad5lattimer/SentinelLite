"""Tests for core.filesystem (PROJECT_SPEC.md section 8 and Run 2)."""

from __future__ import annotations

import os
import sys

import pytest

from core.filesystem import enumerate_files, hash_directory
from core.hasher import calculate_sha256


def _write(root, relative_path: str, content: bytes = b"data") -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_enumerate_files_finds_nested_files(tmp_path):
    _write(tmp_path, "file1.txt")
    _write(tmp_path, "Documents/report.docx")
    _write(tmp_path, "Documents/notes.txt")
    _write(tmp_path, "Config/settings.ini")

    result = enumerate_files(tmp_path)
    relative = {p.relative_to(tmp_path).as_posix() for p in result.paths}

    assert relative == {
        "file1.txt",
        "Documents/report.docx",
        "Documents/notes.txt",
        "Config/settings.ini",
    }
    assert result.errors == []


def test_enumerate_files_on_empty_directory(tmp_path):
    result = enumerate_files(tmp_path)

    assert result.paths == []
    assert result.errors == []


def test_enumerate_files_rejects_non_directory(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"data")

    with pytest.raises(NotADirectoryError):
        enumerate_files(file_path)


def test_hash_directory_produces_file_records(tmp_path):
    _write(tmp_path, "a.txt", b"hello")
    _write(tmp_path, "sub/b.txt", b"world")

    records, errors = hash_directory(tmp_path)

    assert errors == []
    by_path = {r.path: r for r in records}
    assert set(by_path) == {"a.txt", "sub/b.txt"}
    assert by_path["a.txt"].sha256 == calculate_sha256(tmp_path / "a.txt")
    assert by_path["a.txt"].size == len(b"hello")
    assert by_path["sub/b.txt"].sha256 == calculate_sha256(tmp_path / "sub" / "b.txt")


def test_hash_directory_uses_posix_relative_paths(tmp_path):
    _write(tmp_path, "sub/dir/file.txt", b"x")

    records, _errors = hash_directory(tmp_path)

    assert records[0].path == "sub/dir/file.txt"
    assert "\\" not in records[0].path


def test_hash_directory_calls_progress_callback(tmp_path):
    _write(tmp_path, "a.txt")
    _write(tmp_path, "b.txt")

    calls: list[tuple[int, str]] = []
    hash_directory(tmp_path, on_progress=lambda done, path: calls.append((done, path)))

    assert [c[0] for c in calls] == [1, 2]
    assert {c[1] for c in calls} == {"a.txt", "b.txt"}


def test_hash_directory_reports_error_for_unreadable_file_without_crashing(tmp_path):
    _write(tmp_path, "good.txt", b"ok")
    bad_dir_as_file = tmp_path / "looks-like-a-file.txt"
    bad_dir_as_file.mkdir()
    # Not a real file; enumerate_files will list files only, so instead
    # simulate an unreadable *file* by deleting it after enumeration would
    # have seen it -- easiest reliable trigger is a broken symlink target,
    # which enumerate_files intentionally skips, so we exercise the error
    # path directly via hash_directory on a file that is removed mid-scan.
    target = tmp_path / "vanishes.txt"
    target.write_bytes(b"temp")

    from core import filesystem as fs_module

    original_calculate = fs_module.calculate_sha256

    def flaky_calculate(path, **kwargs):
        if path.name == "vanishes.txt":
            raise fs_module.FileHashError(path, OSError("simulated read failure"))
        return original_calculate(path, **kwargs)

    fs_module.calculate_sha256 = flaky_calculate
    try:
        records, errors = hash_directory(tmp_path)
    finally:
        fs_module.calculate_sha256 = original_calculate

    error_paths = {e.path for e in errors}
    record_paths = {r.path for r in records}
    assert "vanishes.txt" in error_paths
    assert "good.txt" in record_paths


def test_enumerate_files_does_not_follow_symlinked_directory(tmp_path):
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    _write(tmp_path, "real/inside.txt")

    monitored = tmp_path / "monitored"
    monitored.mkdir()
    _write(monitored, "top.txt")

    link = monitored / "linked"
    try:
        link.symlink_to(real_dir, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are not supported in this environment.")

    result = enumerate_files(monitored)
    relative = {p.relative_to(monitored).as_posix() for p in result.paths}

    assert relative == {"top.txt"}


def test_enumerate_files_skips_symlinked_file(tmp_path):
    target = tmp_path / "outside.txt"
    target.write_bytes(b"data")

    monitored = tmp_path / "monitored"
    monitored.mkdir()
    _write(monitored, "top.txt")
    link = monitored / "link.txt"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are not supported in this environment.")

    result = enumerate_files(monitored)
    relative = {p.relative_to(monitored).as_posix() for p in result.paths}

    assert relative == {"top.txt"}
