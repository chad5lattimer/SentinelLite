"""Run 2 tests: recursive filesystem enumeration and FileRecord
production (PROJECT_SPEC.md section 27, "Hashing and Filesystem
Engine"). Not explicitly listed among the section 5 test filenames, but
required to exercise ``core/filesystem.py``, which Run 2 introduces.
"""

from __future__ import annotations

import os
import sys

import pytest

from core.filesystem import build_file_records, iter_file_paths
from core.models import FileRecord


def _write(path, content: bytes = b"content"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_enumerates_files_recursively(tmp_path):
    _write(tmp_path / "file1.txt")
    _write(tmp_path / "Documents" / "report.docx")
    _write(tmp_path / "Documents" / "notes.txt")
    _write(tmp_path / "Config" / "settings.ini")

    found = {p.relative_to(tmp_path).as_posix() for p in iter_file_paths(tmp_path)}

    assert found == {
        "file1.txt",
        "Documents/report.docx",
        "Documents/notes.txt",
        "Config/settings.ini",
    }


def test_empty_directory_yields_no_files(tmp_path):
    assert list(iter_file_paths(tmp_path)) == []


def test_build_file_records_produces_expected_records(tmp_path):
    _write(tmp_path / "a.txt", b"hello")
    _write(tmp_path / "nested" / "b.txt", b"world")

    result = build_file_records(tmp_path)

    assert result.errors == []
    assert len(result.records) == 2
    assert all(isinstance(record, FileRecord) for record in result.records)

    by_path = {record.path: record for record in result.records}
    assert set(by_path) == {"a.txt", "nested/b.txt"}
    assert by_path["a.txt"].size == 5
    assert by_path["nested/b.txt"].size == 5
    # Relative paths must use forward slashes regardless of platform.
    assert "\\" not in by_path["nested/b.txt"].path


def test_build_file_records_hash_matches_direct_hash(tmp_path):
    from core.hasher import calculate_sha256

    file_path = tmp_path / "a.txt"
    _write(file_path, b"hello world")

    result = build_file_records(tmp_path)

    assert result.records[0].sha256 == calculate_sha256(file_path)


def test_unreadable_file_is_recorded_as_error_and_scan_continues(tmp_path, monkeypatch):
    _write(tmp_path / "good.txt", b"fine")
    _write(tmp_path / "bad.txt", b"also fine on disk")

    import core.filesystem as filesystem_module

    real_calculate_sha256 = filesystem_module.calculate_sha256

    def fake_calculate_sha256(file_path, chunk_size):
        if file_path.name == "bad.txt":
            raise PermissionError("Permission denied")
        return real_calculate_sha256(file_path, chunk_size)

    monkeypatch.setattr(filesystem_module, "calculate_sha256", fake_calculate_sha256)

    result = build_file_records(tmp_path)

    assert [r.path for r in result.records] == ["good.txt"]
    assert len(result.errors) == 1
    assert result.errors[0].path == "bad.txt"
    assert "Permission denied" in result.errors[0].message


@pytest.mark.skipif(sys.platform.startswith("win"), reason="symlinks handled differently on Windows")
def test_symlinked_file_is_skipped_not_followed(tmp_path):
    _write(tmp_path / "real.txt", b"target content")
    link_path = tmp_path / "link.txt"
    try:
        os.symlink(tmp_path / "real.txt", link_path)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported in this environment")

    found = {p.relative_to(tmp_path).as_posix() for p in iter_file_paths(tmp_path)}

    assert found == {"real.txt"}


@pytest.mark.skipif(sys.platform.startswith("win"), reason="symlinks handled differently on Windows")
def test_symlinked_directory_is_not_descended_into(tmp_path):
    real_dir = tmp_path / "real_dir"
    real_dir.mkdir()
    _write(real_dir / "inside.txt", b"content")

    try:
        os.symlink(real_dir, tmp_path / "linked_dir", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported in this environment")

    found = {p.relative_to(tmp_path).as_posix() for p in iter_file_paths(tmp_path)}

    assert found == {"real_dir/inside.txt"}
