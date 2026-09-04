"""Run 2 tests: recursive enumeration + hashing (PROJECT_SPEC.md section 27
acceptance criteria: enumerate a directory, hash every readable file,
produce FileRecord objects, continue after inaccessible files).
"""

from __future__ import annotations

import pytest

from core.filesystem import enumerate_and_hash, iter_files
from core.hasher import calculate_sha256
from core.models import FileAccessError, FileRecord


def _make_tree(root):
    (root / "file1.txt").write_bytes(b"one")
    (root / "file2.pdf").write_bytes(b"two")
    (root / "Documents").mkdir()
    (root / "Documents" / "report.docx").write_bytes(b"three")
    (root / "Documents" / "notes.txt").write_bytes(b"four")
    (root / "Config").mkdir()
    (root / "Config" / "settings.ini").write_bytes(b"five")


def test_iter_files_finds_all_files_recursively(tmp_path):
    _make_tree(tmp_path)

    found = {p.relative_to(tmp_path).as_posix() for p in iter_files(tmp_path)}

    assert found == {
        "file1.txt",
        "file2.pdf",
        "Documents/report.docx",
        "Documents/notes.txt",
        "Config/settings.ini",
    }


def test_iter_files_skips_symlinked_files_by_default(tmp_path):
    target = tmp_path / "real.txt"
    target.write_bytes(b"data")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported in this environment")

    found = {p.name for p in iter_files(tmp_path)}

    assert "real.txt" in found
    assert "link.txt" not in found


def test_iter_files_skips_symlinked_directories_by_default(tmp_path):
    real_dir = tmp_path / "real_dir"
    real_dir.mkdir()
    (real_dir / "inside.txt").write_bytes(b"data")
    link_dir = tmp_path / "link_dir"
    try:
        link_dir.symlink_to(real_dir, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported in this environment")

    found = {p.relative_to(tmp_path).as_posix() for p in iter_files(tmp_path)}

    assert found == {"real_dir/inside.txt"}


def test_enumerate_and_hash_produces_file_records(tmp_path):
    _make_tree(tmp_path)

    records, errors = enumerate_and_hash(tmp_path)

    assert errors == []
    assert len(records) == 5
    assert all(isinstance(r, FileRecord) for r in records)

    by_path = {r.path: r for r in records}
    assert by_path["file1.txt"].sha256 == calculate_sha256(tmp_path / "file1.txt")
    assert by_path["Documents/notes.txt"].size == len(b"four")


def test_enumerate_and_hash_reports_progress(tmp_path):
    _make_tree(tmp_path)
    calls = []

    enumerate_and_hash(
        tmp_path,
        progress_callback=lambda done, total, path: calls.append((done, total, path)),
    )

    assert len(calls) == 5
    assert calls[-1][0] == 5
    assert all(total == 5 for _, total, _ in calls)


def test_enumerate_and_hash_continues_after_unreadable_file(tmp_path, monkeypatch):
    _make_tree(tmp_path)

    unreadable_path = (tmp_path / "Documents" / "notes.txt").resolve()
    real_calculate_sha256 = calculate_sha256

    def fake_calculate_sha256(file_path, chunk_size=1024 * 1024):
        if file_path.resolve() == unreadable_path:
            raise PermissionError(f"Permission denied: {file_path}")
        return real_calculate_sha256(file_path, chunk_size=chunk_size)

    monkeypatch.setattr("core.filesystem.calculate_sha256", fake_calculate_sha256)

    records, errors = enumerate_and_hash(tmp_path)

    # The scan must not crash and must still process every other file.
    assert len(records) == 4
    assert len(errors) == 1
    assert isinstance(errors[0], FileAccessError)
    assert errors[0].path == "Documents/notes.txt"
    assert "Permission denied" in errors[0].message


def test_enumerate_and_hash_handles_file_deleted_mid_scan(tmp_path):
    _make_tree(tmp_path)
    doomed = tmp_path / "file2.pdf"

    # Simulate a TOCTOU race: the file is deleted between being listed and
    # being read/stat'd.
    import core.filesystem as filesystem_module

    original_iter_files = filesystem_module.iter_files

    def iter_files_then_delete(root, follow_symlinks=False):
        for path in original_iter_files(root, follow_symlinks=follow_symlinks):
            if path == doomed:
                doomed.unlink()
            yield path

    filesystem_module.iter_files = iter_files_then_delete
    try:
        records, errors = enumerate_and_hash(tmp_path)
    finally:
        filesystem_module.iter_files = original_iter_files

    assert any(e.path == "file2.pdf" for e in errors)
    assert not any(r.path == "file2.pdf" for r in records)
    assert len(records) + len(errors) == 5


def test_enumerate_and_hash_empty_directory(tmp_path):
    records, errors = enumerate_and_hash(tmp_path)

    assert records == []
    assert errors == []
