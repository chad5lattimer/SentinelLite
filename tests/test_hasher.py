"""Tests for core.hasher, per PROJECT_SPEC.md section 19 (Hashing):

    - Same file produces same hash.
    - Modified file produces different hash.
    - Empty file can be hashed.
    - Large file can be hashed.
"""

from __future__ import annotations

import hashlib

import pytest

from core.hasher import calculate_sha256


def test_same_file_produces_same_hash(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"hello world")

    first = calculate_sha256(file_path)
    second = calculate_sha256(file_path)

    assert first == second
    # Cross-check against hashlib directly so the test doesn't just
    # compare the function against itself.
    assert first == hashlib.sha256(b"hello world").hexdigest()


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

    result = calculate_sha256(file_path)

    assert result == hashlib.sha256(b"").hexdigest()


def test_large_file_can_be_hashed(tmp_path):
    file_path = tmp_path / "large.bin"
    chunk = b"0123456789abcdef" * 1024  # 16 KiB
    with open(file_path, "wb") as f:
        for _ in range(400):  # ~6.25 MiB total
            f.write(chunk)

    # Use a small chunk size to force multiple incremental reads even in
    # a modest-sized test file.
    result = calculate_sha256(file_path, chunk_size=4096)

    expected = hashlib.sha256()
    with open(file_path, "rb") as f:
        expected.update(f.read())

    assert result == expected.hexdigest()


def test_chunk_size_does_not_affect_result(tmp_path):
    file_path = tmp_path / "data.bin"
    file_path.write_bytes(b"x" * 10_000)

    default_chunk = calculate_sha256(file_path)
    tiny_chunk = calculate_sha256(file_path, chunk_size=1)
    huge_chunk = calculate_sha256(file_path, chunk_size=10_000_000)

    assert default_chunk == tiny_chunk == huge_chunk


def test_missing_file_raises_oserror(tmp_path):
    missing = tmp_path / "does_not_exist.txt"

    with pytest.raises(OSError):
        calculate_sha256(missing)


def test_invalid_chunk_size_raises_value_error(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"data")

    with pytest.raises(ValueError):
        calculate_sha256(file_path, chunk_size=0)
