"""Run 2 tests: SHA-256 hashing (PROJECT_SPEC.md section 19 -- Hashing).

Covers: identical content -> identical hash, changed content -> changed
hash, empty files, large files hashed incrementally, and error behavior
on missing files / invalid chunk sizes.
"""

from __future__ import annotations

import hashlib
import os

import pytest

from core.hasher import calculate_sha256


def test_same_file_produces_same_hash(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"hello world")

    assert calculate_sha256(file_path) == calculate_sha256(file_path)


def test_modified_file_produces_different_hash(tmp_path):
    file_path = tmp_path / "a.txt"

    file_path.write_bytes(b"original content")
    original_hash = calculate_sha256(file_path)

    file_path.write_bytes(b"different content")
    modified_hash = calculate_sha256(file_path)

    assert original_hash != modified_hash


def test_empty_file_can_be_hashed(tmp_path):
    file_path = tmp_path / "empty.txt"
    file_path.write_bytes(b"")

    assert calculate_sha256(file_path) == hashlib.sha256(b"").hexdigest()


def test_large_file_is_hashed_incrementally(tmp_path):
    # Larger than the chunk size used below, so this only passes if the
    # implementation actually reads in multiple chunks and accumulates
    # the digest correctly across them.
    file_path = tmp_path / "large.bin"
    data = os.urandom(5 * 1024 * 1024)  # 5 MiB
    file_path.write_bytes(data)

    expected = hashlib.sha256(data).hexdigest()
    assert calculate_sha256(file_path, chunk_size=64 * 1024) == expected


def test_hash_matches_hashlib_reference(tmp_path):
    file_path = tmp_path / "ref.txt"
    content = b"The quick brown fox jumps over the lazy dog"
    file_path.write_bytes(content)

    assert calculate_sha256(file_path) == hashlib.sha256(content).hexdigest()


def test_missing_file_raises_oserror(tmp_path):
    missing = tmp_path / "does_not_exist.txt"

    with pytest.raises(OSError):
        calculate_sha256(missing)


def test_invalid_chunk_size_raises_value_error(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"data")

    with pytest.raises(ValueError):
        calculate_sha256(file_path, chunk_size=0)
