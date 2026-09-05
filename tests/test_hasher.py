"""Run 2 tests: SHA-256 hashing (PROJECT_SPEC.md section 19 -- Hashing).

Covers:
    - Same file produces same hash.
    - Modified file produces different hash.
    - Empty file can be hashed.
    - Large file can be hashed (incrementally, across multiple chunks).
"""

from __future__ import annotations

import hashlib

import pytest

from core.hasher import DEFAULT_CHUNK_SIZE, calculate_sha256


def test_same_file_produces_same_hash(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"hello sentinel")

    first = calculate_sha256(file_path)
    second = calculate_sha256(file_path)

    assert first == second
    assert first == hashlib.sha256(b"hello sentinel").hexdigest()


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

    digest = calculate_sha256(file_path)

    assert digest == hashlib.sha256(b"").hexdigest()


def test_large_file_can_be_hashed_incrementally(tmp_path):
    # Larger than the default 1 MiB chunk size, so hashing necessarily
    # spans multiple read/update cycles.
    file_path = tmp_path / "large.bin"
    chunk = b"S" * 4096
    with open(file_path, "wb") as f:
        for _ in range(1024):  # 4 MiB total
            f.write(chunk)

    expected = hashlib.sha256()
    with open(file_path, "rb") as f:
        expected.update(f.read())

    digest = calculate_sha256(file_path, chunk_size=64 * 1024)

    assert digest == expected.hexdigest()


def test_chunk_size_does_not_affect_result(tmp_path):
    file_path = tmp_path / "b.txt"
    file_path.write_bytes(b"x" * 10_000)

    small_chunks = calculate_sha256(file_path, chunk_size=17)
    default_chunks = calculate_sha256(file_path, chunk_size=DEFAULT_CHUNK_SIZE)

    assert small_chunks == default_chunks


def test_missing_file_raises_oserror(tmp_path):
    with pytest.raises(OSError):
        calculate_sha256(tmp_path / "does_not_exist.txt")


def test_invalid_chunk_size_rejected(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"data")

    with pytest.raises(ValueError):
        calculate_sha256(file_path, chunk_size=0)
