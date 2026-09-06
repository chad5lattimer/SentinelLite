"""Run 2 tests: recursive enumeration and FileRecord production
(PROJECT_SPEC.md section 27 - Hashing and Filesystem Engine)."""

from __future__ import annotations

import hashlib
import os
import sys

import pytest

from core.filesystem import enumerate_files
from core.models import FileRecord


def _write(path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_enumerate_flat_directory_produces_file_records(tmp_path):
    _write(tmp_path / "file1.txt", b"one")
    _write(tmp_path / "file2.pdf", b"two")

    result = enumerate_files(tmp_path)

    assert result.errors == []
    assert {record.path for record in result.records} == {"file1.txt", "file2.pdf"}
    for record in result.records:
        assert isinstance(record, FileRecord)
        assert len(record.sha256) == 64


def test_enumerate_recurses_into_subdirectories(tmp_path):
    _write(tmp_path / "file1.txt", b"root")
    _write(tmp_path / "Documents" / "report.docx", b"doc")
    _write(tmp_path / "Documents" / "notes.txt", b"notes")
    _write(tmp_path / "Config" / "settings.ini", b"config")

    result = enumerate_files(tmp_path)

    assert {record.path for record in result.records} == {
        "file1.txt",
        "Documents/report.docx",
        "Documents/notes.txt",
        "Config/settings.ini",
    }
    assert result.errors == []


def test_relative_paths_use_forward_slashes(tmp_path):
    _write(tmp_path / "a" / "b" / "c.txt", b"data")

    result = enumerate_files(tmp_path)

    assert result.records[0].path == "a/b/c.txt"
    assert "\\" not in result.records[0].path


def test_file_record_hash_matches_content(tmp_path):
    content = b"exact content to hash"
    _write(tmp_path / "file.txt", content)

    result = enumerate_files(tmp_path)

    assert len(result.records) == 1
    assert result.records[0].sha256 == hashlib.sha256(content).hexdigest()
    assert result.records[0].size == len(content)


def test_empty_directory_produces_no_records(tmp_path):
    result = enumerate_files(tmp_path)

    assert result.records == []
    assert result.errors == []


def test_nonexistent_root_raises(tmp_path):
    with pytest.raises(NotADirectoryError):
        enumerate_files(tmp_path / "does_not_exist")


@pytest.mark.skipif(
    sys.platform.startswith("win") or os.geteuid() == 0,
    reason="Requires POSIX permission enforcement as a non-root user.",
)
def test_unreadable_file_is_recorded_as_error_and_scan_continues(tmp_path):
    _write(tmp_path / "readable.txt", b"ok")
    secret = tmp_path / "secret.txt"
    _write(secret, b"secret")
    secret.chmod(0o000)

    try:
        result = enumerate_files(tmp_path)

        assert {record.path for record in result.records} == {"readable.txt"}
        assert len(result.errors) == 1
        assert result.errors[0].path == "secret.txt"
    finally:
        secret.chmod(0o644)


@pytest.mark.skipif(
    sys.platform.startswith("win") or os.geteuid() == 0,
    reason="Requires POSIX permission enforcement as a non-root user.",
)
def test_unreadable_directory_is_recorded_as_error_and_scan_continues(tmp_path):
    _write(tmp_path / "readable.txt", b"ok")
    locked_dir = tmp_path / "Locked"
    _write(locked_dir / "inside.txt", b"hidden")
    locked_dir.chmod(0o000)

    try:
        result = enumerate_files(tmp_path)

        assert {record.path for record in result.records} == {"readable.txt"}
        assert len(result.errors) == 1
        assert "Locked" in result.errors[0].path
    finally:
        locked_dir.chmod(0o755)


@pytest.mark.skipif(
    sys.platform.startswith("win"), reason="Symlinks require elevated privileges on Windows."
)
def test_symlinks_are_not_followed(tmp_path):
    _write(tmp_path / "real.txt", b"real content")
    target_dir = tmp_path / "real_dir"
    target_dir.mkdir()
    _write(target_dir / "inside.txt", b"inside content")

    (tmp_path / "link_to_file.txt").symlink_to(tmp_path / "real.txt")
    (tmp_path / "link_to_dir").symlink_to(target_dir, target_is_directory=True)

    result = enumerate_files(tmp_path)

    paths = {record.path for record in result.records}
    assert paths == {"real.txt", "real_dir/inside.txt"}
    assert "link_to_file.txt" not in paths
    assert not any(path.startswith("link_to_dir") for path in paths)
