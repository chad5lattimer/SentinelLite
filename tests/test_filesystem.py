"""Run 2 tests: recursive filesystem enumeration and file-record building
(PROJECT_SPEC.md section 27 -- Hashing and Filesystem Engine).

Covers: recursive enumeration, correct FileRecord contents, symbolic
links not being followed (section 8.2), and inaccessible files being
recorded as errors instead of aborting the scan (sections 7.3, 8.3).
"""

from __future__ import annotations

import os

import pytest

from core.filesystem import build_file_records, iter_files
from core.hasher import calculate_sha256
from core.models import FileAccessError, FileRecord


def _make_tree(base):
    """Build the example tree from PROJECT_SPEC.md section 8."""
    (base / "file1.txt").write_text("one")
    (base / "file2.pdf").write_text("two")
    (base / "Documents").mkdir()
    (base / "Documents" / "report.docx").write_text("report")
    (base / "Documents" / "notes.txt").write_text("notes")
    (base / "Config").mkdir()
    (base / "Config" / "settings.ini").write_text("ini")


EXPECTED_RELATIVE_PATHS = {
    "file1.txt",
    "file2.pdf",
    "Documents/report.docx",
    "Documents/notes.txt",
    "Config/settings.ini",
}


def test_iter_files_recursively_enumerates(tmp_path):
    _make_tree(tmp_path)

    found = {p.relative_to(tmp_path).as_posix() for p in iter_files(tmp_path)}

    assert found == EXPECTED_RELATIVE_PATHS


def test_build_file_records_hashes_every_file(tmp_path):
    _make_tree(tmp_path)

    result = build_file_records(tmp_path)

    assert result.errors == []
    assert {record.path for record in result.records} == EXPECTED_RELATIVE_PATHS

    by_path = {record.path: record for record in result.records}
    file1 = by_path["file1.txt"]
    assert isinstance(file1, FileRecord)
    assert file1.sha256 == calculate_sha256(tmp_path / "file1.txt")
    assert file1.size == (tmp_path / "file1.txt").stat().st_size
    assert file1.modified_time == pytest.approx((tmp_path / "file1.txt").stat().st_mtime)


def test_build_file_records_uses_relative_posix_paths(tmp_path):
    _make_tree(tmp_path)

    result = build_file_records(tmp_path)

    for record in result.records:
        assert not record.path.startswith("/")
        assert "\\" not in record.path


def test_empty_directory_produces_no_records(tmp_path):
    result = build_file_records(tmp_path)

    assert result.records == []
    assert result.errors == []


def test_unreadable_file_is_recorded_as_error_not_raised(tmp_path, monkeypatch):
    _make_tree(tmp_path)

    real_calculate_sha256 = calculate_sha256

    def fake_calculate_sha256(file_path, chunk_size=None):
        if file_path.name == "notes.txt":
            raise PermissionError(f"[Errno 13] Permission denied: '{file_path}'")
        if chunk_size is None:
            return real_calculate_sha256(file_path)
        return real_calculate_sha256(file_path, chunk_size=chunk_size)

    monkeypatch.setattr("core.filesystem.calculate_sha256", fake_calculate_sha256)

    result = build_file_records(tmp_path)

    assert len(result.errors) == 1
    error = result.errors[0]
    assert isinstance(error, FileAccessError)
    assert error.path == "Documents/notes.txt"
    assert "Permission denied" in error.message

    # The scan continues -- every other file is still recorded.
    remaining = EXPECTED_RELATIVE_PATHS - {"Documents/notes.txt"}
    assert {record.path for record in result.records} == remaining


@pytest.mark.skipif(
    os.name == "nt" or hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="POSIX permission bits do not block root, and behave "
    "differently on Windows.",
)
def test_permission_denied_file_via_real_chmod(tmp_path):
    _make_tree(tmp_path)
    secret = tmp_path / "secret.txt"
    secret.write_text("classified")
    secret.chmod(0o000)

    try:
        result = build_file_records(tmp_path)
    finally:
        secret.chmod(0o644)  # restore so tmp_path cleanup can remove it

    assert "secret.txt" in {error.path for error in result.errors}
    assert "secret.txt" not in {record.path for record in result.records}


def test_symlinked_directory_is_not_followed(tmp_path):
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    (real_dir / "f.txt").write_text("data")
    link_dir = tmp_path / "link"
    try:
        link_dir.symlink_to(real_dir, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are not supported in this environment.")

    found = {p.relative_to(tmp_path).as_posix() for p in iter_files(tmp_path)}

    assert found == {"real/f.txt"}


def test_symlinked_file_is_skipped(tmp_path):
    target = tmp_path / "target.txt"
    target.write_text("data")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are not supported in this environment.")

    found = {p.relative_to(tmp_path).as_posix() for p in iter_files(tmp_path)}

    assert found == {"target.txt"}
