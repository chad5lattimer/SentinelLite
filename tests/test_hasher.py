"""Run 2 tests: hashing and filesystem enumeration engine.

Covers PROJECT_SPEC.md section 19 ("Hashing") plus enumeration and
permission-error handling for ``core.filesystem``.
"""

from __future__ import annotations

import hashlib
import os
import stat

import pytest

from core.filesystem import collect_file_records, iter_file_paths
from core.hasher import calculate_sha256
from core.models import FileError, FileRecord

# ---------------------------------------------------------------------------
# Hashing (core.hasher)
# ---------------------------------------------------------------------------


def test_same_file_produces_same_hash(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"hello world")

    assert calculate_sha256(file_path) == calculate_sha256(file_path)


def test_hash_matches_hashlib_reference(tmp_path):
    file_path = tmp_path / "a.txt"
    content = b"the quick brown fox jumps over the lazy dog"
    file_path.write_bytes(content)

    assert calculate_sha256(file_path) == hashlib.sha256(content).hexdigest()


def test_modified_file_produces_different_hash(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"original content")
    original_hash = calculate_sha256(file_path)

    file_path.write_bytes(b"changed content")
    modified_hash = calculate_sha256(file_path)

    assert original_hash != modified_hash


def test_empty_file_can_be_hashed(tmp_path):
    file_path = tmp_path / "empty.txt"
    file_path.write_bytes(b"")

    assert calculate_sha256(file_path) == hashlib.sha256(b"").hexdigest()


def test_large_file_can_be_hashed_with_small_chunk_size(tmp_path):
    file_path = tmp_path / "large.bin"
    content = os.urandom(1024 * 64)  # 64 KiB, hashed 1 KiB at a time below.
    file_path.write_bytes(content)

    result = calculate_sha256(file_path, chunk_size=1024)

    assert result == hashlib.sha256(content).hexdigest()


def test_missing_file_raises_oserror(tmp_path):
    with pytest.raises(OSError):
        calculate_sha256(tmp_path / "does_not_exist.txt")


def test_chunk_size_must_be_positive(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"data")

    with pytest.raises(ValueError):
        calculate_sha256(file_path, chunk_size=0)


# ---------------------------------------------------------------------------
# Enumeration and hashing together (core.filesystem)
# ---------------------------------------------------------------------------


def test_enumerate_finds_all_files_recursively(tmp_path):
    (tmp_path / "file1.txt").write_bytes(b"one")
    nested = tmp_path / "Documents"
    nested.mkdir()
    (nested / "notes.txt").write_bytes(b"two")

    paths = sorted(p.relative_to(tmp_path).as_posix() for p in iter_file_paths(tmp_path))

    assert paths == ["Documents/notes.txt", "file1.txt"]


def test_collect_file_records_produces_expected_records(tmp_path):
    (tmp_path / "file1.txt").write_bytes(b"hello")
    nested = tmp_path / "Documents"
    nested.mkdir()
    (nested / "notes.txt").write_bytes(b"world")

    records, errors = collect_file_records(tmp_path)

    assert errors == []
    assert len(records) == 2
    by_path = {record.path: record for record in records}
    assert set(by_path) == {"file1.txt", "Documents/notes.txt"}

    file1 = by_path["file1.txt"]
    assert isinstance(file1, FileRecord)
    assert file1.sha256 == hashlib.sha256(b"hello").hexdigest()
    assert file1.size == 5
    assert file1.modified_time > 0


def test_collect_file_records_on_empty_directory(tmp_path):
    records, errors = collect_file_records(tmp_path)

    assert records == []
    assert errors == []


def test_unreadable_file_becomes_error_and_scan_continues(tmp_path):
    if os.name == "nt":
        pytest.skip("POSIX permission bits are not meaningful on Windows.")
    if os.geteuid() == 0:
        pytest.skip("Running as root ignores file permission bits.")

    readable = tmp_path / "readable.txt"
    readable.write_bytes(b"fine")

    unreadable = tmp_path / "unreadable.txt"
    unreadable.write_bytes(b"secret")
    unreadable.chmod(0)

    try:
        records, errors = collect_file_records(tmp_path)
    finally:
        # Restore permissions so pytest's tmp_path cleanup can remove it.
        unreadable.chmod(stat.S_IRUSR | stat.S_IWUSR)

    assert len(records) == 1
    assert records[0].path == "readable.txt"

    assert len(errors) == 1
    assert isinstance(errors[0], FileError)
    assert errors[0].path == "unreadable.txt"
    assert errors[0].message


def test_symlinked_file_is_skipped_by_default(tmp_path):
    if os.name == "nt":
        pytest.skip("Symlink creation requires elevated privileges on Windows.")

    target = tmp_path / "target.txt"
    target.write_bytes(b"target content")

    link = tmp_path / "link.txt"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are not supported in this environment.")

    records, errors = collect_file_records(tmp_path)

    assert errors == []
    paths = {record.path for record in records}
    assert paths == {"target.txt"}


def test_inaccessible_subdirectory_does_not_abort_scan(tmp_path):
    if os.name == "nt":
        pytest.skip("POSIX permission bits are not meaningful on Windows.")
    if os.geteuid() == 0:
        pytest.skip("Running as root ignores directory permission bits.")

    (tmp_path / "visible.txt").write_bytes(b"data")

    blocked_dir = tmp_path / "blocked"
    blocked_dir.mkdir()
    (blocked_dir / "hidden.txt").write_bytes(b"secret")
    blocked_dir.chmod(0)

    try:
        records, errors = collect_file_records(tmp_path)
    finally:
        blocked_dir.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

    paths = {record.path for record in records}
    assert paths == {"visible.txt"}
    assert errors == []
