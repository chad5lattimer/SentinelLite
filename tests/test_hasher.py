"""Run 2 tests: SHA-256 hashing (PROJECT_SPEC.md section 19 "Hashing")."""

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


def test_known_sha256_vector(tmp_path):
    # SHA-256("abc") is a well-known test vector.
    file_path = tmp_path / "abc.txt"
    file_path.write_bytes(b"abc")

    assert calculate_sha256(file_path) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_empty_file_can_be_hashed(tmp_path):
    file_path = tmp_path / "empty.txt"
    file_path.write_bytes(b"")

    digest = calculate_sha256(file_path)

    # SHA-256 of zero bytes is a fixed, well-known value.
    assert digest == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_large_file_can_be_hashed_with_small_chunk_size(tmp_path):
    file_path = tmp_path / "large.bin"
    # Write a few MiB so hashing spans many chunks, and use a tiny chunk
    # size to force multiple reads.
    payload = b"S" * (1024 * 1024) + b"L" * (1024 * 1024)
    file_path.write_bytes(payload)

    whole_read_digest = calculate_sha256(file_path, chunk_size=len(payload))
    chunked_digest = calculate_sha256(file_path, chunk_size=4096)

    assert whole_read_digest == chunked_digest


def test_calculate_sha256_missing_file_raises_oserror(tmp_path):
    missing = tmp_path / "does_not_exist.txt"

    with pytest.raises(OSError):
        calculate_sha256(missing)


def test_calculate_sha256_rejects_non_positive_chunk_size(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"data")

    with pytest.raises(ValueError):
        calculate_sha256(file_path, chunk_size=0)
