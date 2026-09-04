"""Tests for core.filesystem (PROJECT_SPEC.md section 19: Baseline/Scanner
prerequisites -- recursive enumeration, hashing, and error handling)."""

from __future__ import annotations

import hashlib
import os
import stat
import sys

import pytest

from core.filesystem import build_file_record, collect_file_records, iter_files
from core.models import FileAccessError, FileRecord


def _make_tree(root):
    (root / "file1.txt").write_bytes(b"one")
    (root / "Documents").mkdir()
    (root / "Documents" / "notes.txt").write_bytes(b"notes")
    (root / "Documents" / "Nested").mkdir()
    (root / "Documents" / "Nested" / "deep.txt").write_bytes(b"deep")
    (root / "Config").mkdir()
    (root / "Config" / "settings.ini").write_bytes(b"[settings]")


def test_iter_files_recursively_finds_all_files(tmp_path):
    _make_tree(tmp_path)

    found = {p.relative_to(tmp_path).as_posix() for p in iter_files(tmp_path)}

    assert found == {
        "file1.txt",
        "Documents/notes.txt",
        "Documents/Nested/deep.txt",
        "Config/settings.ini",
    }


def test_iter_files_does_not_yield_directories(tmp_path):
    _make_tree(tmp_path)

    for path in iter_files(tmp_path):
        assert path.is_file()


def test_build_file_record_uses_relative_posix_path(tmp_path):
    (tmp_path / "Documents").mkdir()
    file_path = tmp_path / "Documents" / "notes.txt"
    file_path.write_bytes(b"notes")

    record = build_file_record(tmp_path, file_path)

    assert isinstance(record, FileRecord)
    assert record.path == "Documents/notes.txt"
    assert record.sha256 == hashlib.sha256(b"notes").hexdigest()
    assert record.size == len(b"notes")
    assert record.modified_time == pytest.approx(file_path.stat().st_mtime)


def test_collect_file_records_hashes_every_file(tmp_path):
    _make_tree(tmp_path)

    outcome = collect_file_records(tmp_path)

    assert outcome.errors == []
    assert {r.path for r in outcome.records} == {
        "file1.txt",
        "Documents/notes.txt",
        "Documents/Nested/deep.txt",
        "Config/settings.ini",
    }
    by_path = {r.path: r for r in outcome.records}
    assert by_path["file1.txt"].sha256 == hashlib.sha256(b"one").hexdigest()


def test_collect_file_records_reports_progress(tmp_path):
    _make_tree(tmp_path)

    seen = []
    collect_file_records(tmp_path, progress_callback=lambda count, path: seen.append((count, path)))

    assert [count for count, _ in seen] == [1, 2, 3, 4]
    assert {path for _, path in seen} == {
        "file1.txt",
        "Documents/notes.txt",
        "Documents/Nested/deep.txt",
        "Config/settings.ini",
    }


def test_collect_file_records_on_empty_directory(tmp_path):
    outcome = collect_file_records(tmp_path)

    assert outcome.records == []
    assert outcome.errors == []


@pytest.mark.skipif(sys.platform.startswith("win") or os.geteuid() == 0, reason="permission bits are not reliably enforceable as root or on Windows")
def test_collect_file_records_continues_after_unreadable_file(tmp_path):
    good = tmp_path / "good.txt"
    good.write_bytes(b"fine")
    bad = tmp_path / "bad.txt"
    bad.write_bytes(b"secret")
    bad.chmod(0)

    try:
        outcome = collect_file_records(tmp_path)
    finally:
        bad.chmod(stat.S_IRUSR | stat.S_IWUSR)

    assert {r.path for r in outcome.records} == {"good.txt"}
    assert len(outcome.errors) == 1
    error = outcome.errors[0]
    assert isinstance(error, FileAccessError)
    assert error.path == "bad.txt"
    assert error.message


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX symlinks used for this test")
def test_symlinked_files_are_skipped_by_default(tmp_path):
    target = tmp_path / "real.txt"
    target.write_bytes(b"real content")
    link = tmp_path / "link.txt"
    link.symlink_to(target)

    outcome = collect_file_records(tmp_path)

    assert {r.path for r in outcome.records} == {"real.txt"}


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX symlinks used for this test")
def test_symlinked_files_are_included_when_explicitly_enabled(tmp_path):
    target = tmp_path / "real.txt"
    target.write_bytes(b"real content")
    link = tmp_path / "link.txt"
    link.symlink_to(target)

    outcome = collect_file_records(tmp_path, follow_symlinks=True)

    assert {r.path for r in outcome.records} == {"real.txt", "link.txt"}
