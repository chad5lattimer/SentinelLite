"""Tests for core/filesystem.py (PROJECT_SPEC.md section 27, Run 2).

Covers: recursive enumeration, FileRecord production (with relative,
forward-slash paths), continuing after inaccessible files, and that
symlinks are not followed by default.
"""

from __future__ import annotations

import os
import sys

import pytest

from core.filesystem import build_file_record, enumerate_files, scan_directory
from core.models import FileAccessError, FileRecord


def _make_tree(root):
    (root / "file1.txt").write_bytes(b"one")
    (root / "file2.pdf").write_bytes(b"two")
    (root / "Documents").mkdir()
    (root / "Documents" / "report.docx").write_bytes(b"report")
    (root / "Documents" / "notes.txt").write_bytes(b"notes")
    (root / "Config").mkdir()
    (root / "Config" / "settings.ini").write_bytes(b"[settings]")


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


def test_enumerate_files_on_empty_directory(tmp_path):
    assert list(enumerate_files(tmp_path)) == []


def test_build_file_record_uses_relative_posix_path(tmp_path):
    _make_tree(tmp_path)
    file_path = tmp_path / "Documents" / "notes.txt"

    record = build_file_record(tmp_path, file_path)

    assert isinstance(record, FileRecord)
    assert record.path == "Documents/notes.txt"
    assert record.size == len(b"notes")
    assert record.sha256  # non-empty hex digest
    assert record.modified_time > 0


def test_scan_directory_produces_a_record_per_file(tmp_path):
    _make_tree(tmp_path)

    records, errors = scan_directory(tmp_path)

    assert errors == []
    assert {r.path for r in records} == {
        "file1.txt",
        "file2.pdf",
        "Documents/report.docx",
        "Documents/notes.txt",
        "Config/settings.ini",
    }


def test_scan_directory_reports_progress(tmp_path):
    _make_tree(tmp_path)
    progress_calls = []

    scan_directory(tmp_path, progress_callback=lambda done, total, path: progress_calls.append((done, total, path)))

    assert len(progress_calls) == 5
    assert all(total == 5 for _, total, _ in progress_calls)
    assert [done for done, _, _ in progress_calls] == [1, 2, 3, 4, 5]


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX permission bits only")
def test_scan_directory_continues_after_unreadable_file(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("Cannot test permission denial while running as root.")

    _make_tree(tmp_path)
    unreadable = tmp_path / "secret.txt"
    unreadable.write_bytes(b"top secret")
    unreadable.chmod(0o000)

    try:
        records, errors = scan_directory(tmp_path)
    finally:
        unreadable.chmod(0o644)  # restore so tmp_path cleanup can remove it

    assert any(e.path == "secret.txt" for e in errors)
    assert all(isinstance(e, FileAccessError) for e in errors)
    # Every other, readable file must still have been hashed.
    record_paths = {r.path for r in records}
    assert "file1.txt" in record_paths
    assert "Documents/notes.txt" in record_paths
    assert "secret.txt" not in record_paths


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX symlinks only")
def test_symlinked_files_are_not_followed_by_default(tmp_path):
    real_target = tmp_path / "real.txt"
    real_target.write_bytes(b"real content")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(real_target)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported in this environment.")

    found = {p.name for p in enumerate_files(tmp_path)}

    assert "real.txt" in found
    assert "link.txt" not in found


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX symlinks only")
def test_symlinked_directories_are_not_followed_by_default(tmp_path):
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    (target_dir / "inside.txt").write_bytes(b"inside")

    linked_dir = tmp_path / "linked"
    try:
        linked_dir.symlink_to(target_dir, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported in this environment.")

    found = {p.relative_to(tmp_path).as_posix() for p in enumerate_files(tmp_path)}

    assert "target/inside.txt" in found
    assert not any(p.startswith("linked/") for p in found)
