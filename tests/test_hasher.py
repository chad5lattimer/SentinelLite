"""Tests for core.hasher (PROJECT_SPEC.md section 19 -- Hashing)."""

from __future__ import annotations

import hashlib

import pytest

from core.hasher import FileHashError, calculate_sha256


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
    new_hash = calculate_sha256(file_path)

    assert original_hash != new_hash


def test_empty_file_can_be_hashed(tmp_path):
    file_path = tmp_path / "empty.txt"
    file_path.write_bytes(b"")

    assert calculate_sha256(file_path) == hashlib.sha256(b"").hexdigest()


def test_large_file_can_be_hashed_with_small_chunk_size(tmp_path):
    file_path = tmp_path / "large.bin"
    content = os_urandom_deterministic(3 * 1024 * 1024 + 17)  # not chunk-aligned
    file_path.write_bytes(content)

    # Force many small reads to exercise the chunked-read loop.
    result = calculate_sha256(file_path, chunk_size=4096)

    assert result == hashlib.sha256(content).hexdigest()


def test_chunk_size_does_not_change_result(tmp_path):
    file_path = tmp_path / "b.txt"
    file_path.write_bytes(b"x" * 10_000)

    small_chunks = calculate_sha256(file_path, chunk_size=1)
    default_chunks = calculate_sha256(file_path)

    assert small_chunks == default_chunks


def test_missing_file_raises_file_hash_error(tmp_path):
    missing = tmp_path / "does-not-exist.txt"

    with pytest.raises(FileHashError):
        calculate_sha256(missing)


def test_unreadable_path_raises_file_hash_error(tmp_path):
    # A directory can never be opened as a file -- this reliably exercises
    # the OSError-handling path (unlike chmod(0), which the test runner's
    # own user, e.g. root, may still be able to read past).
    directory_path = tmp_path / "a-directory"
    directory_path.mkdir()

    with pytest.raises(FileHashError):
        calculate_sha256(directory_path)


def test_invalid_chunk_size_raises_value_error(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"data")

    with pytest.raises(ValueError):
        calculate_sha256(file_path, chunk_size=0)


def os_urandom_deterministic(size: int) -> bytes:
    """Deterministic pseudo-random bytes (avoids importing os for this)."""
    import random

    rng = random.Random(1234)
    return bytes(rng.getrandbits(8) for _ in range(size))
