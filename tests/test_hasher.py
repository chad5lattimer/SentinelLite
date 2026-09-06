"""Hashing tests for Run 2 -- Hashing and Filesystem Engine.

Covers PROJECT_SPEC.md section 19 "Hashing" minimum test coverage:
same file -> same hash, modified file -> different hash, empty file, and
large (chunked) file hashing.
"""

from __future__ import annotations

import hashlib

import pytest

from core.hasher import calculate_sha256


def test_same_file_produces_same_hash(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_text("SentinelLite integrity test content")

    first = calculate_sha256(file_path)
    second = calculate_sha256(file_path)

    assert first == second
    assert len(first) == 64  # hex-encoded SHA-256 digest


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


def test_large_file_can_be_hashed_in_chunks(tmp_path):
    file_path = tmp_path / "large.bin"
    payload = b"0123456789abcdef" * 100_000  # 1.6 MB
    file_path.write_bytes(payload)

    # Use a chunk size much smaller than the file so several reads occur.
    result = calculate_sha256(file_path, chunk_size=4096)

    assert result == hashlib.sha256(payload).hexdigest()


def test_hash_matches_hashlib_reference(tmp_path):
    file_path = tmp_path / "ref.txt"
    content = b"reference content for cross-checking against hashlib directly"
    file_path.write_bytes(content)

    assert calculate_sha256(file_path) == hashlib.sha256(content).hexdigest()


def test_missing_file_raises_oserror(tmp_path):
    missing = tmp_path / "does_not_exist.txt"

    with pytest.raises(OSError):
        calculate_sha256(missing)


def test_invalid_chunk_size_rejected(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_text("content")

    with pytest.raises(ValueError):
        calculate_sha256(file_path, chunk_size=0)
