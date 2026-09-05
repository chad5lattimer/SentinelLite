"""Run 2 tests: recursive filesystem enumeration and FileRecord production
(PROJECT_SPEC.md sections 8 and 27).

Covers:
    - Recursive enumeration across nested directories.
    - Relative, forward-slash paths in produced FileRecords.
    - Permission errors are recorded, not raised (scan continues).
    - Symbolic links are not followed by default.
"""

from __future__ import annotations

import os
import sys

import pytest

from core.filesystem import build_file_records, iter_files
from core.hasher import calculate_sha256


def test_enumerates_nested_files(tmp_path):
    (tmp_path / "Documents").mkdir()
    (tmp_path / "file1.txt").write_bytes(b"one")
    (tmp_path / "Documents" / "report.docx").write_bytes(b"two")
    (tmp_path / "Documents" / "notes.txt").write_bytes(b"three")

    result = build_file_records(tmp_path)

    paths = {record.path for record in result.records}
    assert paths == {"file1.txt", "Documents/report.docx", "Documents/notes.txt"}
    assert result.errors == []


def test_file_records_have_correct_hash_size_and_relative_path(tmp_path):
    sub = tmp_path / "Config"
    sub.mkdir()
    target = sub / "settings.ini"
    target.write_bytes(b"key=value")

    result = build_file_records(tmp_path)

    assert len(result.records) == 1
    record = result.records[0]
    assert record.path == "Config/settings.ini"
    assert record.sha256 == calculate_sha256(target)
    assert record.size == target.stat().st_size
    assert record.modified_time == pytest.approx(target.stat().st_mtime)


def test_empty_directory_produces_no_records(tmp_path):
    result = build_file_records(tmp_path)

    assert result.records == []
    assert result.errors == []


def test_unreadable_file_recorded_as_error_and_scan_continues(tmp_path):
    if os.name == "nt" or os.geteuid() == 0:
        pytest.skip("Permission bits are not enforced for root or on Windows.")

    readable = tmp_path / "readable.txt"
    readable.write_bytes(b"ok")

    unreadable = tmp_path / "secret.txt"
    unreadable.write_bytes(b"top secret")
    unreadable.chmod(0o000)

    try:
        result = build_file_records(tmp_path)
    finally:
        unreadable.chmod(0o644)  # restore so tmp_path can be cleaned up

    assert {record.path for record in result.records} == {"readable.txt"}
    assert len(result.errors) == 1
    assert result.errors[0].path == "secret.txt"
    assert result.errors[0].message


@pytest.mark.skipif(sys.platform.startswith("win"), reason="symlink semantics differ on Windows")
def test_symlinked_file_not_followed_by_default(tmp_path):
    target = tmp_path / "real.txt"
    target.write_bytes(b"data")
    link = tmp_path / "link.txt"
    link.symlink_to(target)

    files = list(iter_files(tmp_path, follow_symlinks=False))

    assert target in files
    assert link not in files


@pytest.mark.skipif(sys.platform.startswith("win"), reason="symlink semantics differ on Windows")
def test_symlinked_directory_not_followed_by_default(tmp_path):
    real_dir = tmp_path / "real_dir"
    real_dir.mkdir()
    (real_dir / "inner.txt").write_bytes(b"data")

    link_dir = tmp_path / "link_dir"
    link_dir.symlink_to(real_dir, target_is_directory=True)

    result = build_file_records(tmp_path)

    assert {record.path for record in result.records} == {"real_dir/inner.txt"}
