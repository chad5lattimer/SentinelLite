"""Tests for core.hasher (PROJECT_SPEC.md section 19 - Hashing).

Covers: identical files hash identically, a modified file hashes
differently, empty files can be hashed, and large files are hashed
without being loaded fully into memory (verified via a small chunk
size so chunking is actually exercised).
"""

from __future__ import annotations

import hashlib

import pytest

from core.hasher import calculate_sha256


def test_same_file_produces_same_hash(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_text("hello world")

    assert calculate_sha256(file_path) == calculate_sha256(file_path)


def test_identical_content_produces_identical_hash(tmp_path):
    first = tmp_path / "a.txt"
    second = tmp_path / "b.txt"
    first.write_text("identical content")
    second.write_text("identical content")

    assert calculate_sha256(first) == calculate_sha256(second)


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
    content = os_urandom_deterministic(5 * 1024 * 1024)  # 5 MiB
    file_path.write_bytes(content)

    # A tiny chunk size forces many read iterations, exercising the
    # incremental/chunked code path (section 7.2) rather than a single
    # whole-file read.
    result = calculate_sha256(file_path, chunk_size=4096)

    assert result == hashlib.sha256(content).hexdigest()


def test_matches_hashlib_reference(tmp_path):
    file_path = tmp_path / "reference.txt"
    content = b"The quick brown fox jumps over the lazy dog"
    file_path.write_bytes(content)

    assert calculate_sha256(file_path) == hashlib.sha256(content).hexdigest()


def test_missing_file_raises_os_error(tmp_path):
    with pytest.raises(OSError):
        calculate_sha256(tmp_path / "does_not_exist.txt")


def test_invalid_chunk_size_rejected(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_text("content")

    with pytest.raises(ValueError):
        calculate_sha256(file_path, chunk_size=0)


def os_urandom_deterministic(size: int) -> bytes:
    """Return deterministic pseudo-random bytes without depending on
    ``os.urandom`` (keeps the test fast and reproducible)."""
    pattern = b"SentinelLite-large-file-test-data-"
    repeats = (size // len(pattern)) + 1
    return (pattern * repeats)[:size]
