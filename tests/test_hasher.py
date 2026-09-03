"""Tests for core.hasher, per PROJECT_SPEC.md section 19 (Hashing)."""

from __future__ import annotations

import pytest

from core.hasher import calculate_sha256


def test_same_file_produces_same_hash(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"identical contents")

    assert calculate_sha256(file_path) == calculate_sha256(file_path)


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

    # Known SHA-256 of the empty string.
    assert (
        calculate_sha256(file_path)
        == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


def test_large_file_can_be_hashed_with_small_chunk_size(tmp_path):
    file_path = tmp_path / "large.bin"
    # A few MiB, hashed with an artificially small chunk size, so this
    # exercises the multi-chunk incremental read path deterministically
    # without needing a slow/huge fixture file.
    content = (b"0123456789abcdef" * 1024) * 200  # ~3.3 MiB
    file_path.write_bytes(content)

    import hashlib

    expected = hashlib.sha256(content).hexdigest()

    assert calculate_sha256(file_path, chunk_size=4096) == expected
    # Chunk size must not affect the result.
    assert calculate_sha256(file_path, chunk_size=1024 * 1024) == expected


def test_hash_uses_sha256_hex_digest_length(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"some data")

    digest = calculate_sha256(file_path)
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


def test_unreadable_file_raises_oserror(tmp_path):
    missing = tmp_path / "does_not_exist.txt"

    with pytest.raises(OSError):
        calculate_sha256(missing)


def test_invalid_chunk_size_rejected(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"data")

    with pytest.raises(ValueError):
        calculate_sha256(file_path, chunk_size=0)
