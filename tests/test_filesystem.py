"""Filesystem engine tests for Run 2 -- Hashing and Filesystem Engine.

Covers PROJECT_SPEC.md section 27 acceptance criteria: recursive
enumeration, `FileRecord` production, and continuing past inaccessible
files/directories rather than aborting the scan.
"""

from __future__ import annotations

import hashlib
import os
import sys

import pytest

from core.filesystem import build_file_records, iter_files
from core.models import FileAccessError, FileRecord


def _write(path, content: str = "content"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_enumerate_is_recursive_and_uses_relative_posix_paths(tmp_path):
    _write(tmp_path / "file1.txt", "one")
    _write(tmp_path / "Documents" / "notes.txt", "two")
    _write(tmp_path / "Documents" / "Nested" / "deep.txt", "three")

    records, errors = build_file_records(tmp_path)

    assert errors == []
    paths = {record.path for record in records}
    assert paths == {"file1.txt", "Documents/notes.txt", "Documents/Nested/deep.txt"}
    # Relative paths must use forward slashes regardless of host OS.
    assert all("\\" not in path for path in paths)


def test_file_records_have_correct_hash_size_and_mtime(tmp_path):
    content = "SentinelLite"
    file_path = tmp_path / "sample.txt"
    _write(file_path, content)

    records, errors = build_file_records(tmp_path)

    assert errors == []
    assert len(records) == 1
    record = records[0]
    assert isinstance(record, FileRecord)
    assert record.path == "sample.txt"
    assert record.sha256 == hashlib.sha256(content.encode()).hexdigest()
    assert record.size == len(content.encode())
    assert record.modified_time == pytest.approx(file_path.stat().st_mtime)


def test_empty_directory_yields_no_records(tmp_path):
    records, errors = build_file_records(tmp_path)

    assert records == []
    assert errors == []


def test_nonexistent_root_raises(tmp_path):
    with pytest.raises(NotADirectoryError):
        build_file_records(tmp_path / "does_not_exist")


def test_unreadable_file_is_reported_and_scan_continues(tmp_path):
    if os.name == "nt" or hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("Permission bits are not enforced for this user/platform.")

    readable = tmp_path / "readable.txt"
    _write(readable, "fine")

    unreadable = tmp_path / "unreadable.txt"
    _write(unreadable, "secret")
    unreadable.chmod(0o000)

    try:
        records, errors = build_file_records(tmp_path)
    finally:
        unreadable.chmod(0o644)  # restore so tmp_path cleanup can remove it

    assert {record.path for record in records} == {"readable.txt"}
    assert len(errors) == 1
    assert isinstance(errors[0], FileAccessError)
    assert errors[0].path == "unreadable.txt"


@pytest.mark.skipif(sys.platform.startswith("win"), reason="symlink semantics differ on Windows")
def test_symlinked_file_is_skipped_by_default(tmp_path):
    target = tmp_path / "target.txt"
    _write(target, "real file")
    link = tmp_path / "link.txt"
    link.symlink_to(target)

    records, errors = build_file_records(tmp_path)

    assert {record.path for record in records} == {"target.txt"}
    assert errors == []


@pytest.mark.skipif(sys.platform.startswith("win"), reason="symlink semantics differ on Windows")
def test_symlinked_directory_is_not_followed_by_default(tmp_path):
    real_dir = tmp_path / "real"
    _write(real_dir / "inside.txt", "content")
    link_dir = tmp_path / "link_dir"
    link_dir.symlink_to(real_dir, target_is_directory=True)

    files = list(iter_files(tmp_path))

    assert {f.name for f in files} == {"inside.txt"}
    assert len([f for f in files if "link_dir" in f.parts]) == 0
