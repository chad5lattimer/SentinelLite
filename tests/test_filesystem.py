"""Tests for core.filesystem, per PROJECT_SPEC.md sections 8 and 27 (Run 2)."""

from __future__ import annotations

import os
import sys

import pytest

from core.filesystem import build_file_record, iter_files, scan_directory
from core.hasher import calculate_sha256
from core.models import FileError, FileRecord


def _make_tree(root):
    (root / "file1.txt").write_bytes(b"one")
    (root / "Documents").mkdir()
    (root / "Documents" / "notes.txt").write_bytes(b"notes")
    (root / "Documents" / "Sub").mkdir()
    (root / "Documents" / "Sub" / "deep.txt").write_bytes(b"deep")


def test_iter_files_recursively_finds_all_files(tmp_path):
    _make_tree(tmp_path)

    found = {p.relative_to(tmp_path).as_posix() for p in iter_files(tmp_path)}

    assert found == {
        "file1.txt",
        "Documents/notes.txt",
        "Documents/Sub/deep.txt",
    }


def test_iter_files_skips_empty_directories_without_error(tmp_path):
    (tmp_path / "Empty").mkdir()

    assert list(iter_files(tmp_path)) == []


def test_build_file_record_uses_relative_posix_path_and_matches_hasher(tmp_path):
    (tmp_path / "Documents").mkdir()
    file_path = tmp_path / "Documents" / "notes.txt"
    file_path.write_bytes(b"notes")

    record = build_file_record(tmp_path, file_path)

    assert isinstance(record, FileRecord)
    assert record.path == "Documents/notes.txt"
    assert record.sha256 == calculate_sha256(file_path)
    assert record.size == file_path.stat().st_size
    assert record.modified_time == pytest.approx(file_path.stat().st_mtime)


def test_scan_directory_produces_records_for_every_file(tmp_path):
    _make_tree(tmp_path)

    records, errors = scan_directory(tmp_path)

    assert errors == []
    assert {r.path for r in records} == {
        "file1.txt",
        "Documents/notes.txt",
        "Documents/Sub/deep.txt",
    }
    assert all(len(r.sha256) == 64 for r in records)


def test_scan_directory_reports_progress(tmp_path):
    _make_tree(tmp_path)

    progress_calls = []
    scan_directory(
        tmp_path,
        on_progress=lambda done, total, current: progress_calls.append((done, total, current)),
    )

    assert len(progress_calls) == 3
    # Every call should report the same total, and "done" should count up.
    totals = {total for _, total, _ in progress_calls}
    assert totals == {3}
    assert [done for done, _, _ in progress_calls] == [1, 2, 3]


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX permission semantics")
@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses permission checks")
def test_scan_directory_continues_after_unreadable_file(tmp_path):
    _make_tree(tmp_path)
    unreadable = tmp_path / "secret.txt"
    unreadable.write_bytes(b"top secret")
    unreadable.chmod(0o000)

    try:
        records, errors = scan_directory(tmp_path)
    finally:
        unreadable.chmod(0o644)

    assert {r.path for r in records} == {
        "file1.txt",
        "Documents/notes.txt",
        "Documents/Sub/deep.txt",
    }
    assert len(errors) == 1
    assert isinstance(errors[0], FileError)
    assert errors[0].path == "secret.txt"


@pytest.mark.skipif(sys.platform.startswith("win"), reason="requires os.symlink support")
def test_symlinked_file_is_not_followed_by_default(tmp_path):
    real_dir = tmp_path / "outside"
    real_dir.mkdir()
    (real_dir / "outside.txt").write_bytes(b"outside contents")

    monitored = tmp_path / "monitored"
    monitored.mkdir()
    (monitored / "inside.txt").write_bytes(b"inside contents")
    try:
        (monitored / "link.txt").symlink_to(real_dir / "outside.txt")
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted in this environment")

    found = {p.relative_to(monitored).as_posix() for p in iter_files(monitored)}

    assert found == {"inside.txt"}


@pytest.mark.skipif(sys.platform.startswith("win"), reason="requires os.symlink support")
def test_symlinked_directory_is_not_followed_by_default(tmp_path):
    real_dir = tmp_path / "outside"
    real_dir.mkdir()
    (real_dir / "outside.txt").write_bytes(b"outside contents")

    monitored = tmp_path / "monitored"
    monitored.mkdir()
    (monitored / "inside.txt").write_bytes(b"inside contents")
    try:
        (monitored / "linked_dir").symlink_to(real_dir, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted in this environment")

    found = {p.relative_to(monitored).as_posix() for p in iter_files(monitored)}

    assert found == {"inside.txt"}
