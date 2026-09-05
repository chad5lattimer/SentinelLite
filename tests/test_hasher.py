"""Tests for the Run 2 hashing and filesystem engine.

Covers PROJECT_SPEC.md section 19 ("Hashing" and part of "Scanner"
setup): SHA-256 correctness/incrementality, and that the filesystem layer
enumerates files, produces FileRecord objects, and continues past
inaccessible files/symlinks instead of raising.
"""

from __future__ import annotations

import os
import sys

import pytest

from core.filesystem import build_file_records, iter_files
from core.hasher import HashError, calculate_sha256
from core.models import FileAccessError, FileRecord

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

    # SHA-256 of zero bytes is a well-known constant.
    assert calculate_sha256(file_path) == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


def test_large_file_can_be_hashed_with_small_chunk_size(tmp_path):
    file_path = tmp_path / "large.bin"
    # Larger than a deliberately tiny chunk size, to exercise multiple
    # incremental reads rather than a single read() call.
    data = os.urandom(256 * 1024)
    file_path.write_bytes(data)

    import hashlib

    expected = hashlib.sha256(data).hexdigest()

    assert calculate_sha256(file_path, chunk_size=1024) == expected
    # Result must not depend on chunk size.
    assert calculate_sha256(file_path, chunk_size=64 * 1024) == expected


def test_hash_missing_file_raises_hash_error(tmp_path):
    missing = tmp_path / "does_not_exist.txt"

    with pytest.raises(HashError):
        calculate_sha256(missing)


def test_hash_chunk_size_must_be_positive(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"data")

    with pytest.raises(ValueError):
        calculate_sha256(file_path, chunk_size=0)


@pytest.mark.skipif(
    sys.platform.startswith("win") or os.geteuid() == 0,
    reason="POSIX permission bits are not enforced for Windows or root.",
)
def test_hash_unreadable_file_raises_hash_error(tmp_path):
    file_path = tmp_path / "secret.txt"
    file_path.write_bytes(b"top secret")
    file_path.chmod(0o000)
    try:
        with pytest.raises(HashError):
            calculate_sha256(file_path)
    finally:
        file_path.chmod(0o644)


# ---------------------------------------------------------------------------
# Filesystem enumeration
# ---------------------------------------------------------------------------


def test_iter_files_enumerates_recursively(tmp_path):
    (tmp_path / "file1.txt").write_bytes(b"1")
    (tmp_path / "Documents").mkdir()
    (tmp_path / "Documents" / "report.docx").write_bytes(b"2")
    (tmp_path / "Documents" / "notes.txt").write_bytes(b"3")
    (tmp_path / "Config").mkdir()
    (tmp_path / "Config" / "settings.ini").write_bytes(b"4")

    found = {p.relative_to(tmp_path).as_posix() for p in iter_files(tmp_path)}

    assert found == {
        "file1.txt",
        "Documents/report.docx",
        "Documents/notes.txt",
        "Config/settings.ini",
    }


def test_build_file_records_produces_expected_records(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"hello")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_bytes(b"world")

    records, errors = build_file_records(tmp_path)

    assert errors == []
    assert len(records) == 2
    assert all(isinstance(r, FileRecord) for r in records)

    by_path = {r.path: r for r in records}
    assert set(by_path) == {"a.txt", "sub/b.txt"}
    assert by_path["a.txt"].sha256 == calculate_sha256(tmp_path / "a.txt")
    assert by_path["a.txt"].size == 5
    assert by_path["sub/b.txt"].sha256 == calculate_sha256(tmp_path / "sub" / "b.txt")


def test_build_file_records_on_empty_directory(tmp_path):
    records, errors = build_file_records(tmp_path)

    assert records == []
    assert errors == []


def test_symlinked_file_is_skipped(tmp_path):
    if sys.platform.startswith("win"):
        pytest.skip("Symlink creation typically requires elevated privileges on Windows.")

    target = tmp_path / "real.txt"
    target.write_bytes(b"data")
    link = tmp_path / "link.txt"
    link.symlink_to(target)

    found = {p.relative_to(tmp_path).as_posix() for p in iter_files(tmp_path)}

    assert found == {"real.txt"}


def test_symlinked_directory_is_not_followed(tmp_path):
    if sys.platform.startswith("win"):
        pytest.skip("Symlink creation typically requires elevated privileges on Windows.")

    real_dir = tmp_path / "real_dir"
    real_dir.mkdir()
    (real_dir / "inside.txt").write_bytes(b"data")

    linked_dir = tmp_path / "linked_dir"
    linked_dir.symlink_to(real_dir, target_is_directory=True)

    found = {p.relative_to(tmp_path).as_posix() for p in iter_files(tmp_path)}

    assert found == {"real_dir/inside.txt"}


@pytest.mark.skipif(
    sys.platform.startswith("win") or os.geteuid() == 0,
    reason="POSIX permission bits are not enforced for Windows or root.",
)
def test_build_file_records_continues_after_unreadable_file(tmp_path):
    readable = tmp_path / "readable.txt"
    readable.write_bytes(b"ok")

    unreadable = tmp_path / "unreadable.txt"
    unreadable.write_bytes(b"secret")
    unreadable.chmod(0o000)

    try:
        records, errors = build_file_records(tmp_path)
    finally:
        unreadable.chmod(0o644)

    assert {r.path for r in records} == {"readable.txt"}
    assert len(errors) == 1
    assert isinstance(errors[0], FileAccessError)
    assert errors[0].path == "unreadable.txt"


@pytest.mark.skipif(
    sys.platform.startswith("win") or os.geteuid() == 0,
    reason="POSIX permission bits are not enforced for Windows or root.",
)
def test_build_file_records_continues_after_unreadable_directory(tmp_path):
    (tmp_path / "visible.txt").write_bytes(b"ok")

    locked_dir = tmp_path / "locked"
    locked_dir.mkdir()
    (locked_dir / "hidden.txt").write_bytes(b"secret")
    locked_dir.chmod(0o000)

    try:
        records, errors = build_file_records(tmp_path)
    finally:
        locked_dir.chmod(0o755)

    # The unreadable directory's contents cannot be enumerated at all,
    # so it does not appear as either a record or a per-file error --
    # but the scan must still complete and return the accessible file.
    assert {r.path for r in records} == {"visible.txt"}
