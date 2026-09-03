"""Tests for core.filesystem (PROJECT_SPEC.md section 27 - Run 2).

Covers recursive enumeration, FileRecord production, and that
inaccessible/unreadable files are recorded as errors rather than aborting
the scan (sections 7.3, 8.1, 8.2, 8.3).
"""

from __future__ import annotations

import hashlib
import os

import pytest

from core.filesystem import build_file_records, enumerate_files
from core.models import FileAccessError, FileRecord


def _make_tree(tmp_path):
    (tmp_path / "file1.txt").write_bytes(b"one")
    (tmp_path / "Documents").mkdir()
    (tmp_path / "Documents" / "notes.txt").write_bytes(b"notes")
    (tmp_path / "Documents" / "Nested").mkdir()
    (tmp_path / "Documents" / "Nested" / "deep.txt").write_bytes(b"deep")
    return tmp_path


def test_enumerate_files_recurses_into_subdirectories(tmp_path):
    root = _make_tree(tmp_path)

    found = {p.relative_to(root).as_posix() for p in enumerate_files(root)}

    assert found == {
        "file1.txt",
        "Documents/notes.txt",
        "Documents/Nested/deep.txt",
    }


def test_enumerate_files_does_not_yield_directories(tmp_path):
    root = _make_tree(tmp_path)

    for path in enumerate_files(root):
        assert path.is_file()


def test_build_file_records_produces_correct_records(tmp_path):
    root = _make_tree(tmp_path)

    records, errors = build_file_records(root)

    assert errors == []
    by_path = {record.path: record for record in records}
    assert set(by_path) == {
        "file1.txt",
        "Documents/notes.txt",
        "Documents/Nested/deep.txt",
    }

    notes_record = by_path["Documents/notes.txt"]
    assert isinstance(notes_record, FileRecord)
    assert notes_record.sha256 == hashlib.sha256(b"notes").hexdigest()
    assert notes_record.size == len(b"notes")
    assert notes_record.modified_time == pytest.approx(
        (root / "Documents" / "notes.txt").stat().st_mtime
    )


def test_build_file_records_uses_forward_slash_relative_paths(tmp_path):
    root = _make_tree(tmp_path)

    records, _errors = build_file_records(root)

    for record in records:
        assert "\\" not in record.path
        assert not record.path.startswith("/")


def test_empty_directory_produces_no_records(tmp_path):
    records, errors = build_file_records(tmp_path)

    assert records == []
    assert errors == []


def test_unreadable_file_is_recorded_as_error_and_scan_continues(tmp_path, monkeypatch):
    root = _make_tree(tmp_path)
    unreadable_relative = "Documents/notes.txt"

    import core.filesystem as filesystem_module

    real_calculate_sha256 = filesystem_module.calculate_sha256

    def fake_calculate_sha256(file_path, chunk_size=None):
        if file_path.name == "notes.txt":
            raise PermissionError(13, "Permission denied", str(file_path))
        return real_calculate_sha256(file_path, chunk_size=chunk_size)

    monkeypatch.setattr(filesystem_module, "calculate_sha256", fake_calculate_sha256)

    records, errors = build_file_records(root)

    assert {r.path for r in records} == {"file1.txt", "Documents/Nested/deep.txt"}
    assert len(errors) == 1
    assert isinstance(errors[0], FileAccessError)
    assert errors[0].path == unreadable_relative
    assert "Permission denied" in errors[0].message


@pytest.mark.skipif(
    os.name == "nt" or os.geteuid() == 0,
    reason="Permission bits are not enforced for root; Windows uses a "
    "different permission model not exercised here.",
)
def test_unreadable_directory_is_recorded_as_error_and_scan_continues(tmp_path):
    root = _make_tree(tmp_path)
    blocked_dir = root / "Documents"
    original_mode = blocked_dir.stat().st_mode
    blocked_dir.chmod(0o000)
    try:
        records, errors = build_file_records(root)
    finally:
        blocked_dir.chmod(original_mode)

    assert {r.path for r in records} == {"file1.txt"}
    assert len(errors) == 1
    assert "Documents" in errors[0].path


def test_symlinked_directory_is_not_followed_by_default(tmp_path):
    root = _make_tree(tmp_path)
    outside = tmp_path.parent / "outside_target"
    outside.mkdir(exist_ok=True)
    (outside / "secret.txt").write_bytes(b"outside root")

    link = root / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are not supported in this environment.")

    records, _errors = build_file_records(root)

    assert "linked/secret.txt" not in {r.path for r in records}
