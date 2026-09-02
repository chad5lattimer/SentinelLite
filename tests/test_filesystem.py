"""Tests for core.filesystem: recursive enumeration, FileRecord
production, permission-error handling, and symlink behavior.

Covers the Run 2 acceptance criteria (PROJECT_SPEC.md section 27): the
engine can enumerate a directory, hash every readable file, produce
FileRecord objects, and continue after inaccessible files.
"""

from __future__ import annotations

import os
import sys

import pytest

from core.filesystem import build_file_record, iter_files, scan_directory
from core.hasher import calculate_sha256
from core.models import FileError, FileRecord


def _make_tree(root):
    (root / "file1.txt").write_bytes(b"one")
    (root / "file2.pdf").write_bytes(b"two")
    (root / "Documents").mkdir()
    (root / "Documents" / "report.docx").write_bytes(b"report")
    (root / "Documents" / "notes.txt").write_bytes(b"notes")
    (root / "Config").mkdir()
    (root / "Config" / "settings.ini").write_bytes(b"[settings]")


def test_iter_files_recursively_enumerates_all_files(tmp_path):
    _make_tree(tmp_path)

    found = {str(p.relative_to(tmp_path).as_posix()) for p in iter_files(tmp_path)}

    assert found == {
        "file1.txt",
        "file2.pdf",
        "Documents/report.docx",
        "Documents/notes.txt",
        "Config/settings.ini",
    }


def test_scan_directory_produces_file_records(tmp_path):
    _make_tree(tmp_path)

    outcome = scan_directory(tmp_path)

    assert len(outcome.records) == 5
    assert outcome.errors == []
    assert all(isinstance(record, FileRecord) for record in outcome.records)

    by_path = {record.path: record for record in outcome.records}
    assert by_path["file1.txt"].sha256 == calculate_sha256(tmp_path / "file1.txt")
    assert by_path["file1.txt"].size == 3
    assert by_path["Documents/notes.txt"].sha256 == calculate_sha256(
        tmp_path / "Documents" / "notes.txt"
    )


def test_build_file_record_uses_relative_posix_path(tmp_path):
    (tmp_path / "sub").mkdir()
    file_path = tmp_path / "sub" / "file.txt"
    file_path.write_bytes(b"content")

    record = build_file_record(tmp_path, file_path)

    assert record.path == "sub/file.txt"
    assert record.sha256 == calculate_sha256(file_path)
    assert record.size == len(b"content")
    assert record.modified_time == pytest.approx(file_path.stat().st_mtime)


def test_scan_directory_handles_empty_directory(tmp_path):
    outcome = scan_directory(tmp_path)

    assert outcome.records == []
    assert outcome.errors == []


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX permission bits only.")
def test_scan_directory_continues_after_unreadable_file(tmp_path):
    (tmp_path / "readable.txt").write_bytes(b"ok")
    unreadable = tmp_path / "unreadable.txt"
    unreadable.write_bytes(b"secret")
    unreadable.chmod(0o000)

    try:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            pytest.skip("Running as root; permission bits are not enforced.")

        outcome = scan_directory(tmp_path)

        assert {record.path for record in outcome.records} == {"readable.txt"}
        assert len(outcome.errors) == 1
        error = outcome.errors[0]
        assert isinstance(error, FileError)
        assert error.path == "unreadable.txt"
        assert error.message
    finally:
        unreadable.chmod(0o644)


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX permission bits only.")
def test_scan_directory_continues_after_unreadable_directory(tmp_path):
    (tmp_path / "readable.txt").write_bytes(b"ok")
    blocked_dir = tmp_path / "blocked"
    blocked_dir.mkdir()
    (blocked_dir / "hidden.txt").write_bytes(b"hidden")
    blocked_dir.chmod(0o000)

    try:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            pytest.skip("Running as root; permission bits are not enforced.")

        outcome = scan_directory(tmp_path)

        # The unreadable directory is skipped (logged), not fatal.
        assert {record.path for record in outcome.records} == {"readable.txt"}
    finally:
        blocked_dir.chmod(0o755)


@pytest.mark.skipif(sys.platform.startswith("win"), reason="os.symlink needs elevated privileges on Windows.")
def test_symlinked_file_is_not_followed(tmp_path):
    target = tmp_path / "target.txt"
    target.write_bytes(b"target contents")
    link = tmp_path / "link.txt"
    link.symlink_to(target)

    found = {p.name for p in iter_files(tmp_path)}

    assert found == {"target.txt"}


@pytest.mark.skipif(sys.platform.startswith("win"), reason="os.symlink needs elevated privileges on Windows.")
def test_symlinked_directory_is_not_traversed(tmp_path):
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    (real_dir / "inside.txt").write_bytes(b"inside")

    monitored = tmp_path / "monitored"
    monitored.mkdir()
    (monitored / "direct.txt").write_bytes(b"direct")
    (monitored / "link_to_real").symlink_to(real_dir, target_is_directory=True)

    found = {p.relative_to(monitored).as_posix() for p in iter_files(monitored)}

    assert found == {"direct.txt"}
