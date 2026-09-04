"""Run 2 tests: hashing and filesystem engine (PROJECT_SPEC.md section 19).

Covers:
    Hashing
        - Same file produces same hash.
        - Modified file produces different hash.
        - Empty file can be hashed.
        - Large file can be hashed (incrementally, across many chunks).
    Filesystem
        - Recursive enumeration finds nested files and reports FileRecords.
        - Symbolic links are skipped rather than followed.
        - A file that becomes unreadable after enumeration does not abort
          the scan -- it is recorded as a FileAccessError and the scan
          continues with the remaining files.
"""

from __future__ import annotations

import hashlib
import os

import pytest

from core.filesystem import build_file_record, enumerate_files, scan_directory
from core.hasher import calculate_sha256
from core.models import FileAccessError, FileRecord

EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def test_same_file_produces_same_hash(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"the quick brown fox")

    assert calculate_sha256(file_path) == calculate_sha256(file_path)


def test_modified_file_produces_different_hash(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"original contents")
    original_hash = calculate_sha256(file_path)

    file_path.write_bytes(b"changed contents")
    modified_hash = calculate_sha256(file_path)

    assert original_hash != modified_hash


def test_empty_file_can_be_hashed(tmp_path):
    file_path = tmp_path / "empty.txt"
    file_path.write_bytes(b"")

    assert calculate_sha256(file_path) == EMPTY_SHA256


def test_large_file_hashed_incrementally_across_chunks(tmp_path):
    # Use a tiny chunk size so a modestly-sized file is read across many
    # chunks, exercising the incremental read loop without needing an
    # actually huge file on disk.
    file_path = tmp_path / "large.bin"
    content = os.urandom(64 * 1024)  # 64 KiB
    file_path.write_bytes(content)

    result = calculate_sha256(file_path, chunk_size=1024)

    assert result == hashlib.sha256(content).hexdigest()


def test_hash_missing_file_raises_oserror(tmp_path):
    with pytest.raises(OSError):
        calculate_sha256(tmp_path / "does_not_exist.txt")


def test_chunk_size_must_be_positive(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"data")

    with pytest.raises(ValueError):
        calculate_sha256(file_path, chunk_size=0)


# ---------------------------------------------------------------------------
# Filesystem enumeration and FileRecord production
# ---------------------------------------------------------------------------


def test_enumerate_files_finds_nested_files(tmp_path):
    (tmp_path / "file1.txt").write_bytes(b"one")
    nested = tmp_path / "Documents"
    nested.mkdir()
    (nested / "report.txt").write_bytes(b"two")
    deeper = nested / "Sub"
    deeper.mkdir()
    (deeper / "notes.txt").write_bytes(b"three")

    found = {p.relative_to(tmp_path).as_posix() for p in enumerate_files(tmp_path)}

    assert found == {"file1.txt", "Documents/report.txt", "Documents/Sub/notes.txt"}


def test_enumerate_files_skips_symlinks(tmp_path):
    target = tmp_path / "real.txt"
    target.write_bytes(b"real")

    link = tmp_path / "link.txt"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are not supported in this environment.")

    found = {p.relative_to(tmp_path).as_posix() for p in enumerate_files(tmp_path)}

    assert found == {"real.txt"}


def test_build_file_record_produces_expected_fields(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"hello world")

    record = build_file_record(tmp_path, file_path)

    assert isinstance(record, FileRecord)
    assert record.path == "a.txt"
    assert record.sha256 == calculate_sha256(file_path)
    assert record.size == len(b"hello world")
    assert record.modified_time == pytest.approx(file_path.stat().st_mtime)


def test_scan_directory_produces_file_records(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"one")
    nested = tmp_path / "Documents"
    nested.mkdir()
    (nested / "b.txt").write_bytes(b"two")

    records, errors = scan_directory(tmp_path)

    assert errors == []
    paths = {record.path for record in records}
    assert paths == {"a.txt", "Documents/b.txt"}


def test_scan_directory_continues_after_unreadable_file(tmp_path, monkeypatch):
    good_file = tmp_path / "good.txt"
    good_file.write_bytes(b"fine")

    # Simulate a file that vanished/became inaccessible between
    # enumeration and hashing (e.g. a permission error) without relying on
    # OS permission bits, which the test runner (root) may not be subject
    # to. This exercises the same OSError-handling path.
    missing_file = tmp_path / "vanished.txt"

    def fake_enumerate_files(root):
        yield good_file
        yield missing_file

    monkeypatch.setattr("core.filesystem.enumerate_files", fake_enumerate_files)

    records, errors = scan_directory(tmp_path)

    assert [record.path for record in records] == ["good.txt"]
    assert len(errors) == 1
    assert isinstance(errors[0], FileAccessError)
    assert errors[0].path == "vanished.txt"
    assert errors[0].error
