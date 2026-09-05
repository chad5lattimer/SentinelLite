"""Tests for core.filesystem, per PROJECT_SPEC.md section 27 (Run 2):

- Enumerate a directory (including nested subdirectories).
- Hash every readable file.
- Produce FileRecord objects with correct relative paths/metadata.
- Continue after inaccessible files (permission errors do not stop the walk).
- Skip symbolic links rather than following them (section 8.2).
"""

from __future__ import annotations

import os
import sys

import pytest

from core.filesystem import enumerate_and_hash
from core.hasher import calculate_sha256
from core.models import FileError, FileRecord


def test_enumerate_empty_directory(tmp_path):
    result = enumerate_and_hash(tmp_path)

    assert result.records == []
    assert result.errors == []


def test_enumerate_recursively_produces_file_records(tmp_path):
    (tmp_path / "file1.txt").write_bytes(b"hello")
    (tmp_path / "Documents").mkdir()
    (tmp_path / "Documents" / "notes.txt").write_bytes(b"notes")
    (tmp_path / "Documents" / "Nested").mkdir()
    (tmp_path / "Documents" / "Nested" / "deep.txt").write_bytes(b"deep")

    result = enumerate_and_hash(tmp_path)

    assert result.errors == []
    paths = {record.path for record in result.records}
    assert paths == {"file1.txt", "Documents/notes.txt", "Documents/Nested/deep.txt"}

    for record in result.records:
        assert isinstance(record, FileRecord)
        assert record.sha256 == calculate_sha256(tmp_path / record.path)
        assert record.size == (tmp_path / record.path).stat().st_size
        assert record.modified_time == (tmp_path / record.path).stat().st_mtime


def test_relative_paths_use_forward_slashes(tmp_path):
    (tmp_path / "Documents").mkdir()
    (tmp_path / "Documents" / "notes.txt").write_bytes(b"notes")

    result = enumerate_and_hash(tmp_path)

    assert result.records[0].path == "Documents/notes.txt"
    assert "\\" not in result.records[0].path


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX permission bits")
@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses permission checks")
def test_unreadable_file_is_reported_as_error_and_scan_continues(tmp_path):
    readable = tmp_path / "readable.txt"
    readable.write_bytes(b"ok")

    unreadable = tmp_path / "secret.txt"
    unreadable.write_bytes(b"secret")
    unreadable.chmod(0o000)

    try:
        result = enumerate_and_hash(tmp_path)
    finally:
        unreadable.chmod(0o644)  # restore so tmp_path cleanup can remove it

    assert {record.path for record in result.records} == {"readable.txt"}
    assert len(result.errors) == 1
    error = result.errors[0]
    assert isinstance(error, FileError)
    assert error.path == "secret.txt"
    assert error.message  # some descriptive message was captured


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX symlinks")
def test_symlinked_file_is_skipped(tmp_path):
    target = tmp_path / "target.txt"
    target.write_bytes(b"content")
    link = tmp_path / "link.txt"
    link.symlink_to(target)

    result = enumerate_and_hash(tmp_path)

    paths = {record.path for record in result.records}
    assert paths == {"target.txt"}
    assert result.errors == []


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX symlinks")
def test_symlinked_directory_is_not_followed(tmp_path):
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    (real_dir / "inside.txt").write_bytes(b"content")

    monitored = tmp_path / "monitored"
    monitored.mkdir()
    (monitored / "file.txt").write_bytes(b"top level")
    (monitored / "link_to_real").symlink_to(real_dir, target_is_directory=True)

    result = enumerate_and_hash(monitored)

    paths = {record.path for record in result.records}
    assert paths == {"file.txt"}


def test_custom_chunk_size_is_honored(tmp_path):
    file_path = tmp_path / "data.bin"
    file_path.write_bytes(os.urandom(2000))

    result = enumerate_and_hash(tmp_path, chunk_size=13)

    assert result.records[0].sha256 == calculate_sha256(file_path, chunk_size=13)
