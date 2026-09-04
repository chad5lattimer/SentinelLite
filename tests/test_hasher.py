"""Tests for core.hasher, per PROJECT_SPEC.md section 19 ("Hashing")."""

from __future__ import annotations

import hashlib

import pytest

from core.hasher import calculate_sha256


def test_same_file_produces_same_hash(tmp_path):
    file_path = tmp_path / "sample.txt"
    file_path.write_bytes(b"hello sentinellite")

    assert calculate_sha256(file_path) == calculate_sha256(file_path)


def test_modified_file_produces_different_hash(tmp_path):
    file_path = tmp_path / "sample.txt"
    file_path.write_bytes(b"original contents")
    original_hash = calculate_sha256(file_path)

    file_path.write_bytes(b"changed contents")
    modified_hash = calculate_sha256(file_path)

    assert original_hash != modified_hash


def test_empty_file_can_be_hashed(tmp_path):
    file_path = tmp_path / "empty.txt"
    file_path.write_bytes(b"")

    assert calculate_sha256(file_path) == hashlib.sha256(b"").hexdigest()


def test_hash_matches_reference_implementation(tmp_path):
    content = os_urandom_like(50_000)
    file_path = tmp_path / "reference.bin"
    file_path.write_bytes(content)

    assert calculate_sha256(file_path) == hashlib.sha256(content).hexdigest()


def test_large_file_hashed_in_chunks(tmp_path):
    """A file larger than the chunk size must still hash correctly, and
    hashing must actually occur across multiple chunked reads (not load
    the whole file at once)."""
    chunk_size = 64
    content = os_urandom_like(chunk_size * 10 + 17)  # not an exact multiple
    file_path = tmp_path / "large.bin"
    file_path.write_bytes(content)

    assert calculate_sha256(file_path, chunk_size=chunk_size) == hashlib.sha256(content).hexdigest()


def test_hashing_uses_incremental_reads(tmp_path, monkeypatch):
    """Verify chunked reads by counting how many times `read()` is called."""
    chunk_size = 10
    content = b"x" * (chunk_size * 5)
    file_path = tmp_path / "chunked.bin"
    file_path.write_bytes(content)

    read_calls = []
    real_open = open

    def counting_open(*args, **kwargs):
        handle = real_open(*args, **kwargs)
        real_read = handle.read

        def counting_read(size=-1):
            data = real_read(size)
            read_calls.append(len(data))
            return data

        handle.read = counting_read
        return handle

    monkeypatch.setattr("builtins.open", counting_open)

    digest = calculate_sha256(file_path, chunk_size=chunk_size)

    assert digest == hashlib.sha256(content).hexdigest()
    # 5 full chunks plus a final empty read signalling EOF.
    assert len(read_calls) == 6
    assert all(count <= chunk_size for count in read_calls)


def test_invalid_chunk_size_rejected(tmp_path):
    file_path = tmp_path / "sample.txt"
    file_path.write_bytes(b"data")

    with pytest.raises(ValueError):
        calculate_sha256(file_path, chunk_size=0)


def test_missing_file_raises_oserror(tmp_path):
    with pytest.raises(OSError):
        calculate_sha256(tmp_path / "does_not_exist.txt")


def os_urandom_like(size: int) -> bytes:
    """Deterministic pseudo-random bytes (avoids relying on `os.urandom`
    output for reproducibility across test runs)."""
    return bytes((i * 2654435761) % 256 for i in range(size))
