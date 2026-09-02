"""Filesystem enumeration tests (PROJECT_SPEC.md section 27: Run 2 --
Hashing and Filesystem Engine).
"""

from __future__ import annotations

import os
import sys

import pytest

from core.filesystem import FileScanError, scan_directory
from core.models import FileRecord

# Simulating a permission denial by chmod-ing a file only works on POSIX,
# and not when running as root (root bypasses the permission bits, so the
# file would still be readable and the test wouldn't actually exercise
# the error path).
_CAN_TEST_PERMISSION_DENIAL = (
    not sys.platform.startswith("win") and hasattr(os, "geteuid") and os.geteuid() != 0
)


def _make_tree(root):
    (root / "file1.txt").write_bytes(b"one")
    (root / "file2.pdf").write_bytes(b"two")
    docs = root / "Documents"
    docs.mkdir()
    (docs / "report.docx").write_bytes(b"report")
    (docs / "notes.txt").write_bytes(b"notes")
    config_dir = root / "Config"
    config_dir.mkdir()
    (config_dir / "settings.ini").write_bytes(b"[settings]")


def test_scan_directory_enumerates_all_files_recursively(tmp_path):
    _make_tree(tmp_path)

    outcome = scan_directory(tmp_path)

    assert outcome.errors == []
    paths = {record.path for record in outcome.records}
    assert paths == {
        "file1.txt",
        "file2.pdf",
        "Documents/report.docx",
        "Documents/notes.txt",
        "Config/settings.ini",
    }


def test_scan_directory_produces_file_records_with_expected_fields(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"hello world")

    outcome = scan_directory(tmp_path)

    assert len(outcome.records) == 1
    record = outcome.records[0]
    assert isinstance(record, FileRecord)
    assert record.path == "a.txt"
    assert record.size == len(b"hello world")
    assert len(record.sha256) == 64
    assert record.modified_time > 0


def test_scan_directory_on_empty_directory(tmp_path):
    outcome = scan_directory(tmp_path)

    assert outcome.records == []
    assert outcome.errors == []


@pytest.mark.skipif(
    not _CAN_TEST_PERMISSION_DENIAL,
    reason="Requires a non-root POSIX user to simulate a permission denial.",
)
def test_scan_directory_continues_after_unreadable_file(tmp_path):
    readable = tmp_path / "readable.txt"
    readable.write_bytes(b"can read this")

    unreadable = tmp_path / "unreadable.txt"
    unreadable.write_bytes(b"cannot read this")
    unreadable.chmod(0o000)

    try:
        outcome = scan_directory(tmp_path)
    finally:
        unreadable.chmod(0o644)  # restore so tmp_path cleanup can remove it

    readable_paths = {record.path for record in outcome.records}
    assert "readable.txt" in readable_paths
    assert "unreadable.txt" not in readable_paths

    assert len(outcome.errors) == 1
    assert isinstance(outcome.errors[0], FileScanError)
    assert outcome.errors[0].path == "unreadable.txt"


def test_scan_directory_skips_symlinked_files(tmp_path):
    target = tmp_path / "target.txt"
    target.write_bytes(b"target content")

    link = tmp_path / "link.txt"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are not supported in this environment.")

    outcome = scan_directory(tmp_path)

    paths = {record.path for record in outcome.records}
    assert paths == {"target.txt"}


def test_scan_directory_skips_symlinked_directories(tmp_path):
    monitored = tmp_path / "monitored"
    monitored.mkdir()
    (monitored / "plain.txt").write_bytes(b"plain")

    external = tmp_path / "external"
    external.mkdir()
    (external / "secret.txt").write_bytes(b"secret")

    link_dir = monitored / "linked"
    try:
        link_dir.symlink_to(external, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are not supported in this environment.")

    outcome = scan_directory(monitored)

    paths = {record.path for record in outcome.records}
    assert paths == {"plain.txt"}
