"""Run 2 tests: SHA-256 hashing (PROJECT_SPEC.md section 19 - Hashing)."""

from __future__ import annotations

import hashlib

import pytest

from core.hasher import HashError, calculate_sha256


def test_same_file_produces_same_hash(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"hello world")

    assert calculate_sha256(file_path) == calculate_sha256(file_path)


def test_modified_file_produces_different_hash(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"original content")
    original_hash = calculate_sha256(file_path)

    file_path.write_bytes(b"changed content")
    modified_hash = calculate_sha256(file_path)

    assert original_hash != modified_hash


def test_known_sha256_value(tmp_path):
    # SHA-256 of the ASCII string "abc" is a well-known test vector.
    file_path = tmp_path / "abc.txt"
    file_path.write_bytes(b"abc")

    assert calculate_sha256(file_path) == hashlib.sha256(b"abc").hexdigest()


def test_empty_file_can_be_hashed(tmp_path):
    file_path = tmp_path / "empty.txt"
    file_path.write_bytes(b"")

    assert calculate_sha256(file_path) == hashlib.sha256(b"").hexdigest()


def test_large_file_can_be_hashed_with_small_chunk_size(tmp_path):
    file_path = tmp_path / "large.bin"
    # 5 MiB of data, hashed with a deliberately small chunk size so the
    # incremental-read loop runs many iterations.
    content = bytes((i % 256 for i in range(5 * 1024 * 1024)))
    file_path.write_bytes(content)

    whole_read_digest = calculate_sha256(file_path, chunk_size=64 * 1024 * 1024)
    chunked_digest = calculate_sha256(file_path, chunk_size=4096)

    assert whole_read_digest == chunked_digest


def test_missing_file_raises_hash_error(tmp_path):
    missing = tmp_path / "does_not_exist.txt"

    with pytest.raises(HashError):
        calculate_sha256(missing)


def test_unreadable_file_raises_hash_error(tmp_path):
    file_path = tmp_path / "secret.txt"
    file_path.write_bytes(b"secret")
    file_path.chmod(0o000)

    try:
        if file_path.read_bytes() == b"secret":
            pytest.skip("Running as a user that bypasses file permissions (e.g. root).")
        with pytest.raises(HashError):
            calculate_sha256(file_path)
    finally:
        file_path.chmod(0o644)


def test_invalid_chunk_size_rejected(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"data")

    with pytest.raises(ValueError):
        calculate_sha256(file_path, chunk_size=0)
