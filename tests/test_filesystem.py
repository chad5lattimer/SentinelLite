"""Tests for core.filesystem: recursive enumeration, FileRecord
collection, symlink handling, and graceful handling of unreadable files
(PROJECT_SPEC.md sections 8 and 27).
"""

from __future__ import annotations

import hashlib
import os

import pytest

from core.filesystem import collect_file_records, iter_files
from core.models import FileError, FileRecord


def _write(path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_iter_files_recurses_subdirectories(tmp_path):
    _write(tmp_path / "file1.txt", b"one")
    _write(tmp_path / "Documents" / "report.txt", b"two")
    _write(tmp_path / "Documents" / "Nested" / "deep.txt", b"three")

    found = {p.relative_to(tmp_path).as_posix() for p in iter_files(tmp_path)}

    assert found == {
        "file1.txt",
        "Documents/report.txt",
        "Documents/Nested/deep.txt",
    }


def test_iter_files_skips_symlinked_file(tmp_path):
    real_file = tmp_path / "real.txt"
    real_file.write_bytes(b"data")
    symlink = tmp_path / "link.txt"
    try:
        symlink.symlink_to(real_file)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are not supported in this environment.")

    found = {p.relative_to(tmp_path).as_posix() for p in iter_files(tmp_path)}

    assert found == {"real.txt"}


def test_iter_files_does_not_follow_symlinked_directory(tmp_path):
    target_dir = tmp_path / "outside"
    target_dir.mkdir()
    (target_dir / "secret.txt").write_bytes(b"should not be reached")

    monitored = tmp_path / "monitored"
    monitored.mkdir()
    link = monitored / "linked_dir"
    try:
        link.symlink_to(target_dir, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are not supported in this environment.")

    found = list(iter_files(monitored))

    assert found == []


def test_collect_file_records_produces_correct_hashes(tmp_path):
    _write(tmp_path / "a.txt", b"alpha")
    _write(tmp_path / "sub" / "b.txt", b"beta")

    result = collect_file_records(tmp_path)

    assert result.errors == []
    by_path = {record.path: record for record in result.records}
    assert set(by_path) == {"a.txt", "sub/b.txt"}

    assert by_path["a.txt"].sha256 == hashlib.sha256(b"alpha").hexdigest()
    assert by_path["a.txt"].size == len(b"alpha")
    assert isinstance(by_path["a.txt"], FileRecord)

    assert by_path["sub/b.txt"].sha256 == hashlib.sha256(b"beta").hexdigest()


def test_collect_file_records_continues_after_unreadable_file(tmp_path, monkeypatch):
    _write(tmp_path / "good.txt", b"readable")
    _write(tmp_path / "bad.txt", b"unreadable")

    import core.filesystem as filesystem_module

    real_calculate_sha256 = filesystem_module.calculate_sha256

    def _flaky_calculate_sha256(file_path, chunk_size=1024 * 1024):
        if file_path.name == "bad.txt":
            raise PermissionError(f"Permission denied: {file_path}")
        return real_calculate_sha256(file_path, chunk_size=chunk_size)

    monkeypatch.setattr(filesystem_module, "calculate_sha256", _flaky_calculate_sha256)

    result = collect_file_records(tmp_path)

    assert [record.path for record in result.records] == ["good.txt"]
    assert result.errors == [FileError(path="bad.txt", message="Permission denied: " + str(tmp_path / "bad.txt"))]


def test_collect_file_records_empty_directory(tmp_path):
    result = collect_file_records(tmp_path)

    assert result.records == []
    assert result.errors == []


def test_collect_file_records_uses_relative_posix_paths(tmp_path):
    _write(tmp_path / "Documents" / "notes.txt", b"data")

    result = collect_file_records(tmp_path)

    assert result.records[0].path == "Documents/notes.txt"
    assert os.sep not in result.records[0].path or os.sep == "/"
