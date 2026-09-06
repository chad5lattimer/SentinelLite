"""Tests for core.hasher (PROJECT_SPEC.md section 19 - Hashing).

Covers:
    - Same file produces same hash.
    - Modified file produces different hash.
    - Empty file can be hashed.
    - Large file can be hashed (multi-chunk, with a small chunk size).
    - Unreadable file raises OSError rather than crashing silently.
"""

from __future__ import annotations

import hashlib
import os
import stat

import pytest

from core.hasher import calculate_sha256


def test_same_file_produces_same_hash(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"hello world")

    assert calculate_sha256(file_path) == calculate_sha256(file_path)


def test_hash_matches_hashlib_reference(tmp_path):
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


def test_large_file_hashed_incrementally_across_multiple_chunks(tmp_path):
    file_path = tmp_path / "large.bin"
    content = os.urandom(1024 * 50)  # 50 KiB
    file_path.write_bytes(content)

    # Force many small chunks to exercise the incremental read loop.
    result = calculate_sha256(file_path, chunk_size=1024)

    assert result == hashlib.sha256(content).hexdigest()


def test_chunk_size_does_not_change_the_result(tmp_path):
    file_path = tmp_path / "data.bin"
    file_path.write_bytes(os.urandom(4096))

    assert calculate_sha256(file_path, chunk_size=16) == calculate_sha256(
        file_path, chunk_size=1024 * 1024
    )


def test_invalid_chunk_size_raises_value_error(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"data")

    with pytest.raises(ValueError):
        calculate_sha256(file_path, chunk_size=0)


def test_missing_file_raises_oserror(tmp_path):
    missing = tmp_path / "does_not_exist.txt"

    with pytest.raises(OSError):
        calculate_sha256(missing)


def test_unreadable_file_raises_oserror(tmp_path):
    if os.name == "nt" or hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("Permission bits are not enforced for root or on Windows.")

    file_path = tmp_path / "secret.txt"
    file_path.write_bytes(b"top secret")
    file_path.chmod(0)

    try:
        with pytest.raises(OSError):
            calculate_sha256(file_path)
    finally:
        file_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
