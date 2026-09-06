"""Tests for core.filesystem (PROJECT_SPEC.md section 27 -- Run 2).

Covers directory enumeration, hashing every readable file into
`FileRecord` objects, continuing past inaccessible files/directories, and
the documented symbolic-link behavior (section 8.2).
"""

from __future__ import annotations

import os
import sys

import pytest

from core.filesystem import collect_file_records, enumerate_files
from core.hasher import calculate_sha256
from core.models import FileAccessError, FileRecord


def _make_tree(root):
    (root / "file1.txt").write_text("file1")
    (root / "Documents").mkdir()
    (root / "Documents" / "notes.txt").write_text("notes")
    (root / "Config").mkdir()
    (root / "Config" / "settings.ini").write_text("[section]\nkey=value")


def test_enumerate_files_finds_all_files_recursively(tmp_path):
    _make_tree(tmp_path)

    found = {p.relative_to(tmp_path).as_posix() for p in enumerate_files(tmp_path)}

    assert found == {"file1.txt", "Documents/notes.txt", "Config/settings.ini"}


def test_collect_file_records_produces_correct_records(tmp_path):
    _make_tree(tmp_path)

    records, errors = collect_file_records(tmp_path)

    assert errors == []
    assert len(records) == 3
    assert all(isinstance(r, FileRecord) for r in records)

    by_path = {r.path: r for r in records}
    assert by_path.keys() == {"file1.txt", "Documents/notes.txt", "Config/settings.ini"}

    expected_hash = calculate_sha256(tmp_path / "file1.txt")
    record = by_path["file1.txt"]
    assert record.sha256 == expected_hash
    assert record.size == (tmp_path / "file1.txt").stat().st_size
    assert record.modified_time == pytest.approx((tmp_path / "file1.txt").stat().st_mtime)


def test_collect_file_records_on_empty_directory(tmp_path):
    records, errors = collect_file_records(tmp_path)

    assert records == []
    assert errors == []


def test_relative_paths_use_forward_slashes(tmp_path):
    (tmp_path / "Documents").mkdir()
    (tmp_path / "Documents" / "report.docx").write_text("report")

    records, _ = collect_file_records(tmp_path)

    assert records[0].path == "Documents/report.docx"


def test_symlinked_file_is_skipped(tmp_path):
    real_file = tmp_path / "real.txt"
    real_file.write_text("real content")
    link_path = tmp_path / "link.txt"

    try:
        link_path.symlink_to(real_file)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are not supported/permitted in this environment.")

    records, errors = collect_file_records(tmp_path)

    assert errors == []
    assert {r.path for r in records} == {"real.txt"}


def test_symlinked_directory_is_not_followed(tmp_path):
    real_dir = tmp_path / "real_dir"
    real_dir.mkdir()
    (real_dir / "inside.txt").write_text("inside")

    link_dir = tmp_path / "link_dir"
    try:
        link_dir.symlink_to(real_dir, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are not supported/permitted in this environment.")

    records, errors = collect_file_records(tmp_path)

    assert errors == []
    assert {r.path for r in records} == {"real_dir/inside.txt"}


@pytest.mark.skipif(
    sys.platform.startswith("win") or os.geteuid() == 0,
    reason="Permission bits behave differently on Windows and are bypassed as root.",
)
def test_unreadable_file_is_reported_as_error_not_raised(tmp_path):
    good_file = tmp_path / "readable.txt"
    good_file.write_text("readable")

    blocked_file = tmp_path / "blocked.txt"
    blocked_file.write_text("secret")
    blocked_file.chmod(0o000)

    try:
        records, errors = collect_file_records(tmp_path)
    finally:
        blocked_file.chmod(0o644)  # restore so tmp_path cleanup can remove it

    assert {r.path for r in records} == {"readable.txt"}
    assert len(errors) == 1
    assert isinstance(errors[0], FileAccessError)
    assert errors[0].path == "blocked.txt"


@pytest.mark.skipif(
    sys.platform.startswith("win") or os.geteuid() == 0,
    reason="Permission bits behave differently on Windows and are bypassed as root.",
)
def test_unreadable_directory_is_skipped_not_raised(tmp_path):
    (tmp_path / "readable.txt").write_text("readable")

    blocked_dir = tmp_path / "blocked_dir"
    blocked_dir.mkdir()
    (blocked_dir / "hidden.txt").write_text("hidden")
    blocked_dir.chmod(0o000)

    try:
        records, errors = collect_file_records(tmp_path)
    finally:
        blocked_dir.chmod(0o755)  # restore so tmp_path cleanup can remove it

    assert {r.path for r in records} == {"readable.txt"}
    assert errors == []
