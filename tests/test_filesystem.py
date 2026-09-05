"""Tests for core.filesystem (PROJECT_SPEC.md section 8: Filesystem
Scanning, and section 19: Testing Requirements)."""

from __future__ import annotations

import hashlib

import pytest

import core.filesystem as filesystem_module
from core.filesystem import enumerate_files, scan_directory
from core.models import FileError, FileRecord


def _write(path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_enumerate_files_recurses_into_subdirectories(tmp_path):
    _write(tmp_path / "file1.txt", b"one")
    _write(tmp_path / "Documents" / "report.docx", b"two")
    _write(tmp_path / "Documents" / "notes.txt", b"three")
    _write(tmp_path / "Config" / "settings.ini", b"four")

    found = {p.relative_to(tmp_path).as_posix() for p in enumerate_files(tmp_path)}

    assert found == {
        "file1.txt",
        "Documents/report.docx",
        "Documents/notes.txt",
        "Config/settings.ini",
    }


def test_scan_directory_produces_file_records(tmp_path):
    _write(tmp_path / "a.txt", b"hello")

    records, errors = scan_directory(tmp_path)

    assert errors == []
    assert len(records) == 1
    record = records[0]
    assert isinstance(record, FileRecord)
    assert record.path == "a.txt"
    assert record.sha256 == hashlib.sha256(b"hello").hexdigest()
    assert record.size == 5
    assert record.modified_time > 0


def test_scan_directory_uses_relative_posix_paths(tmp_path):
    _write(tmp_path / "Documents" / "notes.txt", b"x")

    records, _ = scan_directory(tmp_path)

    assert records[0].path == "Documents/notes.txt"


def test_scan_directory_continues_after_unreadable_file(tmp_path, monkeypatch):
    _write(tmp_path / "good.txt", b"readable")
    _write(tmp_path / "bad.txt", b"unreadable")

    real_hash = filesystem_module.calculate_sha256

    def fake_hash(path, chunk_size=filesystem_module.DEFAULT_HASH_CHUNK_SIZE):
        if path.name == "bad.txt":
            raise PermissionError("Permission denied")
        return real_hash(path, chunk_size=chunk_size)

    # scan_directory calls calculate_sha256 via the module-level name
    # imported into core.filesystem, so patch it there rather than on
    # core.hasher (simulates an unreadable file without depending on the
    # test process's real OS permissions, e.g. when running as root).
    monkeypatch.setattr(filesystem_module, "calculate_sha256", fake_hash)

    records, errors = scan_directory(tmp_path)

    assert {record.path for record in records} == {"good.txt"}
    assert len(errors) == 1
    assert isinstance(errors[0], FileError)
    assert errors[0].path == "bad.txt"
    assert "Permission denied" in errors[0].message


def test_enumerate_files_skips_symlinked_files(tmp_path):
    target = tmp_path / "real.txt"
    target.write_bytes(b"data")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported in this environment.")

    found = {p.name for p in enumerate_files(tmp_path)}

    assert found == {"real.txt"}


def test_enumerate_files_skips_symlinked_directories(tmp_path):
    real_dir = tmp_path / "RealDir"
    real_dir.mkdir()
    (real_dir / "inside.txt").write_bytes(b"data")

    link_dir = tmp_path / "LinkDir"
    try:
        link_dir.symlink_to(real_dir, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported in this environment.")

    found = {p.relative_to(tmp_path).as_posix() for p in enumerate_files(tmp_path)}

    assert found == {"RealDir/inside.txt"}


def test_scan_directory_handles_empty_directory(tmp_path):
    records, errors = scan_directory(tmp_path)

    assert records == []
    assert errors == []


def test_scan_directory_handles_missing_root(tmp_path):
    missing_root = tmp_path / "does_not_exist"

    records, errors = scan_directory(missing_root)

    assert records == []
    assert errors == []
