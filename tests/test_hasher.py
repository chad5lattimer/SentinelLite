"""Tests for core/hasher.py (PROJECT_SPEC.md section 19: Hashing).

Covers: identical files produce identical hashes, a modified file produces
a different hash, empty files can be hashed, and large files are hashed
correctly and incrementally (chunk-size independent).
"""

from __future__ import annotations

import hashlib

import pytest

from core.hasher import EMPTY_FILE_SHA256, calculate_sha256


def test_same_file_produces_same_hash(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"hello world")

    assert calculate_sha256(file_path) == calculate_sha256(file_path)


def test_modified_file_produces_different_hash(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"original content")
    original_hash = calculate_sha256(file_path)

    file_path.write_bytes(b"changed content")
    modified_hash = calculate_sha256(file_path)

    assert original_hash != modified_hash


def test_hash_matches_hashlib_reference(tmp_path):
    file_path = tmp_path / "a.txt"
    data = b"The quick brown fox jumps over the lazy dog"
    file_path.write_bytes(data)

    assert calculate_sha256(file_path) == hashlib.sha256(data).hexdigest()


def test_empty_file_can_be_hashed(tmp_path):
    file_path = tmp_path / "empty.txt"
    file_path.write_bytes(b"")

    assert calculate_sha256(file_path) == EMPTY_FILE_SHA256
    assert calculate_sha256(file_path) == hashlib.sha256(b"").hexdigest()


def test_large_file_can_be_hashed_incrementally(tmp_path):
    file_path = tmp_path / "large.bin"
    # Larger than a small test chunk size, so hashing exercises multiple
    # incremental read cycles without writing a huge file to disk.
    data = b"\x00\x01\x02\x03" * (64 * 1024)
    file_path.write_bytes(data)

    expected = hashlib.sha256(data).hexdigest()

    # A tiny chunk size forces many incremental reads.
    assert calculate_sha256(file_path, chunk_size=1024) == expected
    # Result must not depend on chunk size.
    assert calculate_sha256(file_path, chunk_size=1024 * 1024) == expected


def test_chunk_size_must_be_positive(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"data")

    with pytest.raises(ValueError):
        calculate_sha256(file_path, chunk_size=0)


def test_missing_file_raises_oserror(tmp_path):
    with pytest.raises(OSError):
        calculate_sha256(tmp_path / "does_not_exist.txt")
