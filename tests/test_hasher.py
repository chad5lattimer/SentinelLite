"""Run 2 tests: SHA-256 hashing (PROJECT_SPEC.md section 19 "Hashing").

Covers: identical content hashes identically, modified content changes
the hash, empty files can be hashed, and large files are hashed
correctly via the chunked read path (not just in one gulp).
"""

from __future__ import annotations

import hashlib

import pytest

from core.hasher import calculate_sha256


def test_same_file_produces_same_hash(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"identical content")

    assert calculate_sha256(file_path) == calculate_sha256(file_path)


def test_identical_content_produces_identical_hash(tmp_path):
    file_a = tmp_path / "a.txt"
    file_b = tmp_path / "b.txt"
    file_a.write_bytes(b"same bytes")
    file_b.write_bytes(b"same bytes")

    assert calculate_sha256(file_a) == calculate_sha256(file_b)


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
    # Use a tiny chunk size so a modestly sized file still exercises the
    # multi-chunk read loop without a slow test.
    file_path = tmp_path / "large.bin"
    content = bytes(range(256)) * 1024  # 256 KiB, deterministic
    file_path.write_bytes(content)

    result = calculate_sha256(file_path, chunk_size=4096)

    assert result == hashlib.sha256(content).hexdigest()


def test_chunk_size_does_not_affect_result(tmp_path):
    file_path = tmp_path / "data.bin"
    file_path.write_bytes(bytes(range(256)) * 100)

    whole_read = calculate_sha256(file_path, chunk_size=10 * 1024 * 1024)
    chunked_read = calculate_sha256(file_path, chunk_size=1)

    assert whole_read == chunked_read


def test_missing_file_raises_oserror(tmp_path):
    with pytest.raises(OSError):
        calculate_sha256(tmp_path / "does-not-exist.txt")


def test_invalid_chunk_size_rejected(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"content")

    with pytest.raises(ValueError):
        calculate_sha256(file_path, chunk_size=0)
