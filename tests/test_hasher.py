"""Tests for core.hasher (PROJECT_SPEC.md section 19 - Hashing)."""

from __future__ import annotations

import pytest

from core.hasher import calculate_sha256


def test_same_file_produces_same_hash(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"hello sentinellite")

    assert calculate_sha256(file_path) == calculate_sha256(file_path)


def test_modified_file_produces_different_hash(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"original content")
    original_hash = calculate_sha256(file_path)

    file_path.write_bytes(b"changed content")
    modified_hash = calculate_sha256(file_path)

    assert original_hash != modified_hash


def test_empty_file_can_be_hashed(tmp_path):
    import hashlib

    file_path = tmp_path / "empty.txt"
    file_path.write_bytes(b"")

    # SHA-256 of zero bytes is a well-known constant; cross-check against
    # hashlib directly computed on empty bytes rather than hard-coding it.
    assert calculate_sha256(file_path) == hashlib.sha256(b"").hexdigest()


def test_large_file_can_be_hashed_with_small_chunk_size(tmp_path):
    file_path = tmp_path / "large.bin"
    # Not truly "large", but exercises multiple read cycles by using a tiny
    # chunk size, proving the file is hashed incrementally rather than in
    # one `read()` call.
    content = bytes(range(256)) * 1000  # 256,000 bytes
    file_path.write_bytes(content)

    import hashlib

    expected = hashlib.sha256(content).hexdigest()

    assert calculate_sha256(file_path, chunk_size=64) == expected


def test_hash_matches_hashlib_reference(tmp_path):
    import hashlib

    file_path = tmp_path / "ref.txt"
    content = b"reference content for cross-check"
    file_path.write_bytes(content)

    assert calculate_sha256(file_path) == hashlib.sha256(content).hexdigest()


def test_nonzero_chunk_size_required(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"data")

    with pytest.raises(ValueError):
        calculate_sha256(file_path, chunk_size=0)


def test_missing_file_raises_oserror(tmp_path):
    missing = tmp_path / "does_not_exist.txt"

    with pytest.raises(OSError):
        calculate_sha256(missing)
