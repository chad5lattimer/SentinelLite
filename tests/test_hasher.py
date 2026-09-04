"""Tests for core.hasher (PROJECT_SPEC.md section 19: Hashing)."""

from __future__ import annotations

import hashlib
import os
import stat
import sys

import pytest

from core.hasher import calculate_sha256


def _write(path, data: bytes):
    path.write_bytes(data)
    return path


def test_same_file_produces_same_hash(tmp_path):
    file_path = _write(tmp_path / "a.txt", b"hello world")

    assert calculate_sha256(file_path) == calculate_sha256(file_path)


def test_hash_matches_hashlib_reference(tmp_path):
    data = b"the quick brown fox jumps over the lazy dog"
    file_path = _write(tmp_path / "a.txt", data)

    assert calculate_sha256(file_path) == hashlib.sha256(data).hexdigest()


def test_modified_file_produces_different_hash(tmp_path):
    file_path = _write(tmp_path / "a.txt", b"version one")
    original = calculate_sha256(file_path)

    _write(file_path, b"version two")
    modified = calculate_sha256(file_path)

    assert original != modified


def test_empty_file_can_be_hashed(tmp_path):
    file_path = _write(tmp_path / "empty.txt", b"")

    assert calculate_sha256(file_path) == hashlib.sha256(b"").hexdigest()


def test_large_file_can_be_hashed_across_multiple_chunks(tmp_path):
    # Force several chunk reads with a small chunk size rather than writing
    # a truly huge file, while still exercising the incremental-read path.
    data = os.urandom(1024 * 50)  # 50 KiB
    file_path = _write(tmp_path / "large.bin", data)

    result = calculate_sha256(file_path, chunk_size=1024)  # 1 KiB chunks

    assert result == hashlib.sha256(data).hexdigest()


def test_hash_result_is_lowercase_hex_of_expected_length(tmp_path):
    file_path = _write(tmp_path / "a.txt", b"hello world")

    digest = calculate_sha256(file_path)

    assert len(digest) == 64
    assert digest == digest.lower()
    int(digest, 16)  # raises ValueError if not valid hex


def test_missing_file_raises_oserror(tmp_path):
    with pytest.raises(OSError):
        calculate_sha256(tmp_path / "does_not_exist.txt")


def test_invalid_chunk_size_raises_value_error(tmp_path):
    file_path = _write(tmp_path / "a.txt", b"data")

    with pytest.raises(ValueError):
        calculate_sha256(file_path, chunk_size=0)


@pytest.mark.skipif(sys.platform.startswith("win") or os.geteuid() == 0, reason="permission bits are not reliably enforceable as root or on Windows")
def test_unreadable_file_raises_permission_error(tmp_path):
    file_path = _write(tmp_path / "secret.txt", b"top secret")
    file_path.chmod(0)

    try:
        with pytest.raises(PermissionError):
            calculate_sha256(file_path)
    finally:
        file_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
