"""Tests for core.filesystem (PROJECT_SPEC.md section 19 / section 8).

Covers recursive enumeration, FileRecord production, permission-error
handling (the scan must continue rather than crash), and that symbolic
links are not followed (section 8.2).
"""

from __future__ import annotations

import os
import sys

import pytest

from core.filesystem import enumerate_files, scan_directory
from core.hasher import calculate_sha256
from core.models import FileError, FileRecord


def _make_tree(root):
    (root / "file1.txt").write_text("one")
    (root / "file2.pdf").write_text("two")
    (root / "Documents").mkdir()
    (root / "Documents" / "report.docx").write_text("report")
    (root / "Documents" / "notes.txt").write_text("notes")
    (root / "Config").mkdir()
    (root / "Config" / "settings.ini").write_text("[settings]")


def test_enumerate_files_finds_all_files_recursively(tmp_path):
    _make_tree(tmp_path)

    found = {p.relative_to(tmp_path).as_posix() for p in enumerate_files(tmp_path)}

    assert found == {
        "file1.txt",
        "file2.pdf",
        "Documents/report.docx",
        "Documents/notes.txt",
        "Config/settings.ini",
    }


def test_scan_directory_produces_file_records(tmp_path):
    _make_tree(tmp_path)

    records, errors = scan_directory(tmp_path)

    assert errors == []
    assert len(records) == 5
    assert all(isinstance(record, FileRecord) for record in records)

    by_path = {record.path: record for record in records}
    expected_hash = calculate_sha256(tmp_path / "file1.txt")
    assert by_path["file1.txt"].sha256 == expected_hash
    assert by_path["file1.txt"].size == (tmp_path / "file1.txt").stat().st_size
    assert by_path["Documents/notes.txt"].path == "Documents/notes.txt"


def test_scan_directory_handles_empty_directory(tmp_path):
    records, errors = scan_directory(tmp_path)

    assert records == []
    assert errors == []


@pytest.mark.skipif(
    sys.platform.startswith("win"), reason="POSIX permission bits don't apply on Windows."
)
@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses permission checks.")
def test_scan_continues_after_unreadable_file(tmp_path):
    readable = tmp_path / "readable.txt"
    unreadable = tmp_path / "unreadable.txt"
    readable.write_text("can read this")
    unreadable.write_text("cannot read this")
    unreadable.chmod(0o000)

    try:
        records, errors = scan_directory(tmp_path)
    finally:
        unreadable.chmod(0o644)

    assert len(errors) == 1
    assert isinstance(errors[0], FileError)
    assert errors[0].path == "unreadable.txt"

    assert len(records) == 1
    assert records[0].path == "readable.txt"


@pytest.mark.skipif(
    sys.platform.startswith("win"), reason="POSIX permission bits don't apply on Windows."
)
@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses permission checks.")
def test_scan_continues_after_unreadable_directory(tmp_path):
    (tmp_path / "readable.txt").write_text("visible")
    locked_dir = tmp_path / "Locked"
    locked_dir.mkdir()
    (locked_dir / "secret.txt").write_text("hidden")
    locked_dir.chmod(0o000)

    try:
        records, errors = scan_directory(tmp_path)
    finally:
        locked_dir.chmod(0o755)

    paths = {record.path for record in records}
    assert "readable.txt" in paths
    assert "Locked/secret.txt" not in paths


@pytest.mark.skipif(
    sys.platform.startswith("win"), reason="symlinks require elevated privileges on Windows."
)
def test_symlinked_file_is_not_followed(tmp_path):
    real_file = tmp_path / "real.txt"
    real_file.write_text("actual content")
    link = tmp_path / "link.txt"
    link.symlink_to(real_file)

    records, errors = scan_directory(tmp_path)

    paths = {record.path for record in records}
    assert "real.txt" in paths
    assert "link.txt" not in paths
    assert errors == []


@pytest.mark.skipif(
    sys.platform.startswith("win"), reason="symlinks require elevated privileges on Windows."
)
def test_symlinked_directory_is_not_followed(tmp_path):
    real_dir = tmp_path / "RealDir"
    real_dir.mkdir()
    (real_dir / "inside.txt").write_text("content")
    link_dir = tmp_path / "LinkedDir"
    link_dir.symlink_to(real_dir, target_is_directory=True)

    records, errors = scan_directory(tmp_path)

    paths = {record.path for record in records}
    assert "RealDir/inside.txt" in paths
    assert not any(path.startswith("LinkedDir") for path in paths)
