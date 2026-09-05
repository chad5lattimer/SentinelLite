"""Run 2 filesystem engine tests (PROJECT_SPEC.md section 27).

Covers: recursive enumeration, FileRecord production, continuing past
unreadable files/directories rather than crashing (sections 7.3 / 8.3),
and the default symlink policy (section 8.2).
"""

from __future__ import annotations

import hashlib
import os
import sys

import pytest

from core.filesystem import EnumerationResult, FileReadError, build_file_records, iter_files
from core.models import FileRecord


def _write(path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_enumerates_files_recursively(tmp_path):
    _write(tmp_path / "file1.txt", b"one")
    _write(tmp_path / "Documents" / "notes.txt", b"two")
    _write(tmp_path / "Config" / "settings.ini", b"three")

    found = {p.relative_to(tmp_path).as_posix() for p in iter_files(tmp_path)}

    assert found == {"file1.txt", "Documents/notes.txt", "Config/settings.ini"}


def test_build_file_records_produces_correct_hashes_and_metadata(tmp_path):
    content = b"hello world"
    _write(tmp_path / "hello.txt", content)

    result = build_file_records(tmp_path)

    assert isinstance(result, EnumerationResult)
    assert len(result.records) == 1
    assert result.errors == []

    record = result.records[0]
    assert isinstance(record, FileRecord)
    assert record.path == "hello.txt"
    assert record.sha256 == hashlib.sha256(content).hexdigest()
    assert record.size == len(content)
    assert record.modified_time == pytest.approx((tmp_path / "hello.txt").stat().st_mtime)


def test_build_file_records_reports_progress(tmp_path):
    _write(tmp_path / "a.txt", b"a")
    _write(tmp_path / "b.txt", b"b")

    progress_calls = []
    build_file_records(
        tmp_path, on_progress=lambda done, total, path: progress_calls.append((done, total, path))
    )

    assert len(progress_calls) == 2
    assert [done for done, _, _ in progress_calls] == [1, 2]
    assert all(total == 2 for _, total, _ in progress_calls)


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX permission bits")
@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permission bits")
def test_unreadable_file_is_recorded_as_error_and_scan_continues(tmp_path):
    _write(tmp_path / "readable.txt", b"fine")
    unreadable = tmp_path / "unreadable.txt"
    _write(unreadable, b"secret")
    unreadable.chmod(0o000)

    try:
        result = build_file_records(tmp_path)
    finally:
        unreadable.chmod(0o644)

    assert len(result.records) == 1
    assert result.records[0].path == "readable.txt"

    assert len(result.errors) == 1
    error = result.errors[0]
    assert isinstance(error, FileReadError)
    assert error.path == "unreadable.txt"
    assert error.message


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX permission bits")
@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permission bits")
def test_unreadable_directory_is_skipped_without_crashing(tmp_path):
    _write(tmp_path / "visible.txt", b"visible")
    blocked_dir = tmp_path / "blocked"
    _write(blocked_dir / "hidden.txt", b"hidden")
    blocked_dir.chmod(0o000)

    try:
        result = build_file_records(tmp_path)
    finally:
        blocked_dir.chmod(0o755)

    assert [record.path for record in result.records] == ["visible.txt"]


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX symlinks need admin rights")
def test_symlinked_file_is_not_followed_by_default(tmp_path):
    _write(tmp_path / "real.txt", b"real content")
    link_path = tmp_path / "link.txt"
    link_path.symlink_to(tmp_path / "real.txt")

    found = {p.relative_to(tmp_path).as_posix() for p in iter_files(tmp_path)}

    assert found == {"real.txt"}


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX symlinks need admin rights")
def test_symlinked_directory_is_not_followed_by_default(tmp_path):
    real_dir = tmp_path / "real_dir"
    _write(real_dir / "inside.txt", b"data")
    (tmp_path / "link_dir").symlink_to(real_dir, target_is_directory=True)

    found = {p.relative_to(tmp_path).as_posix() for p in iter_files(tmp_path)}

    assert found == {"real_dir/inside.txt"}
