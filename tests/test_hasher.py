"""Tests for core.hasher (PROJECT_SPEC.md section 19: Hashing)."""

from __future__ import annotations

import hashlib

import pytest

from core.hasher import calculate_sha256


def test_same_file_produces_same_hash(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"hello world")

    assert calculate_sha256(file_path) == calculate_sha256(file_path)


def test_modified_file_produces_different_hash(tmp_path):
    file_path = tmp_path / "b.txt"
    file_path.write_bytes(b"version one")
    first_hash = calculate_sha256(file_path)

    file_path.write_bytes(b"version two, which is longer")
    second_hash = calculate_sha256(file_path)

    assert first_hash != second_hash


def test_empty_file_can_be_hashed(tmp_path):
    file_path = tmp_path / "empty.txt"
    file_path.write_bytes(b"")

    assert calculate_sha256(file_path) == hashlib.sha256(b"").hexdigest()


def test_large_file_hashes_correctly_with_small_chunk_size(tmp_path):
    file_path = tmp_path / "large.bin"
    # ~1.28 MB of deterministic, non-repeating-byte content -- larger than
    # a single small chunk, to exercise the incremental read loop.
    content = bytes(range(256)) * 5000
    file_path.write_bytes(content)

    expected = hashlib.sha256(content).hexdigest()

    assert calculate_sha256(file_path, chunk_size=17) == expected
    # Also matches the configured default chunk size.
    assert calculate_sha256(file_path) == expected


def test_calculate_sha256_returns_lowercase_hex_digest(tmp_path):
    file_path = tmp_path / "c.txt"
    file_path.write_bytes(b"digest format check")

    digest = calculate_sha256(file_path)

    assert len(digest) == 64
    assert digest == digest.lower()
    int(digest, 16)  # raises ValueError if not valid hex


def test_calculate_sha256_rejects_non_positive_chunk_size(tmp_path):
    file_path = tmp_path / "d.txt"
    file_path.write_bytes(b"x")

    with pytest.raises(ValueError):
        calculate_sha256(file_path, chunk_size=0)


def test_calculate_sha256_missing_file_raises_oserror(tmp_path):
    missing = tmp_path / "does_not_exist.txt"

    with pytest.raises(OSError):
        calculate_sha256(missing)
