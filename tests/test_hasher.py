"""Tests for core.hasher, per PROJECT_SPEC.md section 19 (Hashing):

- Same file produces same hash.
- Modified file produces different hash.
- Empty file can be hashed.
- Large file can be hashed (exercised across multiple chunk boundaries).
"""

from __future__ import annotations

import hashlib

import pytest

from core.hasher import calculate_sha256


def test_same_file_produces_same_hash(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"the quick brown fox")

    first = calculate_sha256(file_path)
    second = calculate_sha256(file_path)

    assert first == second
    assert first == hashlib.sha256(b"the quick brown fox").hexdigest()


def test_modified_file_produces_different_hash(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"original content")
    original_hash = calculate_sha256(file_path)

    file_path.write_bytes(b"modified content")
    modified_hash = calculate_sha256(file_path)

    assert original_hash != modified_hash


def test_empty_file_can_be_hashed(tmp_path):
    file_path = tmp_path / "empty.txt"
    file_path.write_bytes(b"")

    digest = calculate_sha256(file_path)

    assert digest == hashlib.sha256(b"").hexdigest()


def test_large_file_can_be_hashed_across_chunk_boundaries(tmp_path):
    # Use a small chunk size so a modestly sized file still spans many
    # chunks, exercising the incremental read loop without writing an
    # actually huge file to disk during tests.
    chunk_size = 16
    data = bytes(range(256)) * 50  # 12,800 bytes -> 800 chunks of 16 bytes
    file_path = tmp_path / "large.bin"
    file_path.write_bytes(data)

    digest = calculate_sha256(file_path, chunk_size=chunk_size)

    assert digest == hashlib.sha256(data).hexdigest()


def test_hash_matches_regardless_of_chunk_size(tmp_path):
    data = os_random_bytes(5000)
    file_path = tmp_path / "chunked.bin"
    file_path.write_bytes(data)

    small_chunks = calculate_sha256(file_path, chunk_size=64)
    large_chunks = calculate_sha256(file_path, chunk_size=1024 * 1024)

    assert small_chunks == large_chunks == hashlib.sha256(data).hexdigest()


def test_missing_file_raises_oserror(tmp_path):
    missing = tmp_path / "does_not_exist.txt"

    with pytest.raises(OSError):
        calculate_sha256(missing)


def test_invalid_chunk_size_raises_value_error(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"data")

    with pytest.raises(ValueError):
        calculate_sha256(file_path, chunk_size=0)


def os_random_bytes(count: int) -> bytes:
    """Small helper to avoid importing `os` at module scope just for this."""
    import os

    return os.urandom(count)
