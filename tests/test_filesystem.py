"""Tests for core.filesystem (PROJECT_SPEC.md section 8 / Run 2).

Covers recursive enumeration, FileRecord production, permission-error
handling (the scan continues after an inaccessible file), and that
symbolic links are not followed.
"""

from __future__ import annotations

import hashlib
import logging
import os
import stat

import pytest

import core.filesystem as filesystem_module
from core.filesystem import scan_directory
from core.models import FileError, FileRecord


def _write(path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_scan_directory_enumerates_nested_files(tmp_path):
    _write(tmp_path / "file1.txt", b"one")
    _write(tmp_path / "Documents" / "notes.txt", b"two")
    _write(tmp_path / "Config" / "settings.ini", b"three")

    records, errors = scan_directory(tmp_path)

    assert errors == []
    paths = {record.path for record in records}
    assert paths == {"file1.txt", "Documents/notes.txt", "Config/settings.ini"}


def test_scan_directory_produces_correct_file_records(tmp_path):
    content = b"hello world"
    _write(tmp_path / "file1.txt", content)

    records, errors = scan_directory(tmp_path)

    assert errors == []
    assert len(records) == 1
    record = records[0]
    assert isinstance(record, FileRecord)
    assert record.path == "file1.txt"
    assert record.sha256 == hashlib.sha256(content).hexdigest()
    assert record.size == len(content)
    assert record.modified_time == pytest.approx((tmp_path / "file1.txt").stat().st_mtime)


def test_scan_directory_uses_forward_slashes_for_relative_paths(tmp_path):
    _write(tmp_path / "a" / "b" / "c.txt", b"data")

    records, _errors = scan_directory(tmp_path)

    assert records[0].path == "a/b/c.txt"
    assert "\\" not in records[0].path


def test_scan_directory_continues_after_permission_error(tmp_path):
    if os.name == "nt" or hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("Permission bits are not enforced for root or on Windows.")

    _write(tmp_path / "readable.txt", b"ok")
    blocked = tmp_path / "blocked.txt"
    _write(blocked, b"secret")
    blocked.chmod(0)

    try:
        records, errors = scan_directory(tmp_path)
    finally:
        blocked.chmod(stat.S_IRUSR | stat.S_IWUSR)

    readable_paths = {record.path for record in records}
    error_paths = {error.path for error in errors}

    assert "readable.txt" in readable_paths
    assert "blocked.txt" in error_paths
    assert isinstance(errors[0], FileError)


def test_scan_directory_does_not_follow_symlinked_directories(tmp_path):
    if os.name == "nt":
        pytest.skip("Symlinks require elevated privileges on Windows.")

    monitored = tmp_path / "monitored"
    outside = tmp_path / "outside"
    _write(monitored / "inside.txt", b"inside")
    _write(outside / "secret.txt", b"outside data")

    try:
        (monitored / "link_to_outside").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation not permitted in this environment.")

    records, _errors = scan_directory(monitored)

    paths = {record.path for record in records}
    assert paths == {"inside.txt"}


def test_scan_directory_does_not_follow_symlinked_files(tmp_path):
    if os.name == "nt":
        pytest.skip("Symlinks require elevated privileges on Windows.")

    target = tmp_path / "real.txt"
    _write(target, b"real content")
    link = tmp_path / "monitored" / "link.txt"
    link.parent.mkdir(parents=True, exist_ok=True)

    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("Symlink creation not permitted in this environment.")

    records, _errors = scan_directory(tmp_path / "monitored")

    assert records == []


def test_scan_directory_reports_progress(tmp_path):
    _write(tmp_path / "a.txt", b"a")
    _write(tmp_path / "b.txt", b"b")

    progress_calls = []
    scan_directory(tmp_path, progress_callback=lambda count, path: progress_calls.append((count, path)))

    assert [count for count, _path in progress_calls] == [1, 2]


def test_scan_directory_rejects_non_directory(tmp_path):
    file_path = tmp_path / "not_a_dir.txt"
    _write(file_path, b"data")

    with pytest.raises(NotADirectoryError):
        scan_directory(file_path)


def test_scan_directory_empty_directory_returns_no_records(tmp_path):
    records, errors = scan_directory(tmp_path)

    assert records == []
    assert errors == []


def test_scan_directory_logs_warning_when_directory_cannot_be_listed(tmp_path, monkeypatch, caplog):
    """Covers the ``onerror`` callback passed to ``os.walk`` (section 8's
    "a permission error must not terminate the scan").

    ``test_scan_directory_continues_after_permission_error`` above exercises
    this behavior via a real ``chmod(0)``, but that test correctly
    ``pytest.skip()``s when running as root (permission bits aren't
    enforced), which is how this container and CI both run -- so the
    ``onerror`` callback itself was never actually invoked by any test.
    Monkeypatching ``os.walk`` to call it directly exercises the real
    callback regardless of the user the tests run as.
    """
    _write(tmp_path / "readable.txt", b"ok")

    real_walk = os.walk

    def fake_walk(root, onerror=None, followlinks=False):
        if onerror is not None:
            onerror(OSError(13, "Permission denied (simulated)", str(tmp_path / "blocked")))
        yield from real_walk(root, onerror=onerror, followlinks=followlinks)

    monkeypatch.setattr(filesystem_module.os, "walk", fake_walk)

    with caplog.at_level(logging.WARNING, logger="core.filesystem"):
        records, errors = scan_directory(tmp_path)

    assert {record.path for record in records} == {"readable.txt"}
    assert errors == []
    assert any("Cannot list directory" in message for message in caplog.messages)


def test_scan_directory_records_error_when_hashing_raises_oserror(tmp_path, monkeypatch):
    """Covers the ``except OSError`` branch around hashing/``stat()`` in
    ``scan_directory`` for a file that enumerates fine but fails to read.

    Same rationale as the ``os.walk`` test above: the existing chmod-based
    test for this path skips under root, so this monkeypatches the hashing
    seam directly to exercise the branch unconditionally.
    """
    _write(tmp_path / "readable.txt", b"ok")
    _write(tmp_path / "unreadable.txt", b"secret")

    real_hash = filesystem_module.calculate_sha256

    def fake_hash(path, **kwargs):
        if path.name == "unreadable.txt":
            raise OSError(13, "Permission denied (simulated)", str(path))
        return real_hash(path, **kwargs)

    monkeypatch.setattr(filesystem_module, "calculate_sha256", fake_hash)

    records, errors = scan_directory(tmp_path)

    assert {record.path for record in records} == {"readable.txt"}
    assert {error.path for error in errors} == {"unreadable.txt"}
    assert isinstance(errors[0], FileError)
    assert "Permission denied" in errors[0].message
