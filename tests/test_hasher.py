"""Tests for core.hasher (PROJECT_SPEC.md section 19 -- Hashing).

Covers:
    - Same file produces the same hash.
    - A modified file produces a different hash.
    - An empty file can be hashed.
    - A large file (spanning multiple chunks) can be hashed correctly.
"""

from __future__ import annotations

import hashlib

import pytest

from core.hasher import calculate_sha256


def test_same_file_produces_same_hash(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_text("hello sentinel")

    assert calculate_sha256(file_path) == calculate_sha256(file_path)


def test_modified_file_produces_different_hash(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_text("original content")
    original_hash = calculate_sha256(file_path)

    file_path.write_text("modified content")
    modified_hash = calculate_sha256(file_path)

    assert original_hash != modified_hash


def test_empty_file_can_be_hashed(tmp_path):
    file_path = tmp_path / "empty.txt"
    file_path.write_bytes(b"")

    assert calculate_sha256(file_path) == hashlib.sha256(b"").hexdigest()


def test_large_file_can_be_hashed_with_small_chunk_size(tmp_path):
    file_path = tmp_path / "large.bin"
    content = os_urandom_deterministic(3 * 1024 * 1024 + 17)  # spans many chunks
    file_path.write_bytes(content)

    # Force many chunk reads by using a tiny chunk size.
    result = calculate_sha256(file_path, chunk_size=4096)

    assert result == hashlib.sha256(content).hexdigest()


def test_hash_matches_hashlib_directly(tmp_path):
    file_path = tmp_path / "known.txt"
    file_path.write_bytes(b"The quick brown fox jumps over the lazy dog")

    assert calculate_sha256(file_path) == hashlib.sha256(
        b"The quick brown fox jumps over the lazy dog"
    ).hexdigest()


def test_chunk_size_does_not_affect_result(tmp_path):
    file_path = tmp_path / "chunked.bin"
    content = os_urandom_deterministic(10_000)
    file_path.write_bytes(content)

    assert calculate_sha256(file_path, chunk_size=1) == calculate_sha256(
        file_path, chunk_size=1024 * 1024
    )


def test_invalid_chunk_size_raises():
    with pytest.raises(ValueError):
        calculate_sha256("unused", chunk_size=0)


def test_missing_file_raises_oserror(tmp_path):
    missing = tmp_path / "does-not-exist.txt"
    with pytest.raises(OSError):
        calculate_sha256(missing)


def os_urandom_deterministic(size: int) -> bytes:
    """Deterministic pseudo-random bytes, so tests are reproducible without
    depending on the OS entropy source for large payloads."""
    return bytes((i * 2654435761) & 0xFF for i in range(size))
