"""Tests for core.hasher, per PROJECT_SPEC.md section 19 (Hashing):

    - Same file produces same hash.
    - Modified file produces different hash.
    - Empty file can be hashed.
    - Large file can be hashed.
"""

from __future__ import annotations

import hashlib
import os

import pytest

from core.hasher import HashError, calculate_sha256


def test_same_file_produces_same_hash(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"hello world")

    assert calculate_sha256(file_path) == calculate_sha256(file_path)


def test_hash_matches_known_sha256(tmp_path):
    file_path = tmp_path / "a.txt"
    content = b"hello world"
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
    # "Large" relative to the chunk size, to exercise multiple read
    # iterations without writing an enormous file in the test suite.
    file_path = tmp_path / "large.bin"
    content = bytes(range(256)) * 10_000  # 2.56 MB
    file_path.write_bytes(content)

    result = calculate_sha256(file_path, chunk_size=4096)

    assert result == hashlib.sha256(content).hexdigest()


def test_hashing_is_incremental_regardless_of_chunk_size(tmp_path):
    file_path = tmp_path / "b.txt"
    file_path.write_bytes(b"x" * 10_000)

    assert calculate_sha256(file_path, chunk_size=1) == calculate_sha256(file_path, chunk_size=1_000_000)


def test_missing_file_raises_hash_error(tmp_path):
    missing_path = tmp_path / "does_not_exist.txt"

    with pytest.raises(HashError):
        calculate_sha256(missing_path)


def test_unreadable_file_raises_hash_error(tmp_path):
    file_path = tmp_path / "no_permission.txt"
    file_path.write_bytes(b"secret")
    file_path.chmod(0o000)

    try:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            pytest.skip("Running as root; permission bits are not enforced.")
        with pytest.raises(HashError):
            calculate_sha256(file_path)
    finally:
        file_path.chmod(0o644)


def test_invalid_chunk_size_rejected(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"data")

    with pytest.raises(ValueError):
        calculate_sha256(file_path, chunk_size=0)
