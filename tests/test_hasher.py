"""Run 2 hashing tests (PROJECT_SPEC.md section 19: Hashing).

Covers: identical content produces identical hashes, modified content
produces a different hash, empty files can be hashed, and hashing works
across multiple chunk boundaries (large-file / chunked-read behavior)
without loading the whole file into memory at once.
"""

from __future__ import annotations

import hashlib

import pytest

from core.hasher import calculate_sha256


def test_same_content_produces_same_hash(tmp_path):
    file_a = tmp_path / "a.txt"
    file_b = tmp_path / "b.txt"
    file_a.write_bytes(b"identical content")
    file_b.write_bytes(b"identical content")

    assert calculate_sha256(file_a) == calculate_sha256(file_b)


def test_modified_file_produces_different_hash(tmp_path):
    file_path = tmp_path / "file.txt"
    file_path.write_bytes(b"original content")
    original_hash = calculate_sha256(file_path)

    file_path.write_bytes(b"changed content")
    modified_hash = calculate_sha256(file_path)

    assert original_hash != modified_hash


def test_empty_file_can_be_hashed(tmp_path):
    file_path = tmp_path / "empty.txt"
    file_path.write_bytes(b"")

    assert calculate_sha256(file_path) == hashlib.sha256(b"").hexdigest()


def test_hash_matches_hashlib_reference(tmp_path):
    content = b"the quick brown fox jumps over the lazy dog" * 100
    file_path = tmp_path / "reference.bin"
    file_path.write_bytes(content)

    assert calculate_sha256(file_path) == hashlib.sha256(content).hexdigest()


def test_large_file_hashes_correctly_across_multiple_chunks(tmp_path):
    # A small chunk size forces many reads for a modestly sized file,
    # exercising the same incremental-read code path a genuinely large
    # file would take (PROJECT_SPEC.md section 7.2) without needing to
    # actually write megabytes of data in a test.
    content = os_urandom_deterministic(5000)
    file_path = tmp_path / "chunked.bin"
    file_path.write_bytes(content)

    result = calculate_sha256(file_path, chunk_size=64)

    assert result == hashlib.sha256(content).hexdigest()


def test_nonexistent_file_raises_oserror(tmp_path):
    with pytest.raises(OSError):
        calculate_sha256(tmp_path / "does_not_exist.txt")


def test_invalid_chunk_size_rejected(tmp_path):
    file_path = tmp_path / "file.txt"
    file_path.write_bytes(b"data")

    with pytest.raises(ValueError):
        calculate_sha256(file_path, chunk_size=0)


def os_urandom_deterministic(size: int) -> bytes:
    """A deterministic byte string of ``size`` bytes for reproducible tests."""
    pattern = bytes(range(256))
    full, remainder = divmod(size, len(pattern))
    return pattern * full + pattern[:remainder]
