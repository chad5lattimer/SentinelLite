"""Hashing tests (PROJECT_SPEC.md section 19: Testing Requirements -- Hashing)."""

from __future__ import annotations

import hashlib

import pytest

from core.hasher import calculate_sha256


def test_same_file_produces_same_hash(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"identical content")

    assert calculate_sha256(file_path) == calculate_sha256(file_path)


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


def test_large_file_can_be_hashed(tmp_path):
    file_path = tmp_path / "large.bin"
    chunk = b"x" * (256 * 1024)
    with open(file_path, "wb") as handle:
        for _ in range(12):  # ~3 MiB: several reads at the 1 MiB default chunk size
            handle.write(chunk)

    expected = hashlib.sha256()
    with open(file_path, "rb") as handle:
        while data := handle.read(1024 * 1024):
            expected.update(data)

    assert calculate_sha256(file_path) == expected.hexdigest()


def test_hash_is_independent_of_chunk_size(tmp_path):
    file_path = tmp_path / "data.bin"
    file_path.write_bytes(bytes(range(256)) * 100)

    default_hash = calculate_sha256(file_path)
    small_chunk_hash = calculate_sha256(file_path, chunk_size=16)

    assert default_hash == small_chunk_hash


def test_invalid_chunk_size_rejected(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"data")

    with pytest.raises(ValueError):
        calculate_sha256(file_path, chunk_size=0)


def test_missing_file_raises_oserror(tmp_path):
    with pytest.raises(OSError):
        calculate_sha256(tmp_path / "does-not-exist.txt")
