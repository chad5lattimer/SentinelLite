"""Tests for core.scanner (PROJECT_SPEC.md section 10 - Scan Algorithm,
section 29 - Run 4).

Covers the exact acceptance scenario from section 29 / section 33 (Final
Acceptance Test):

    A.txt -> modified
    B.txt -> deleted
    C.txt -> unchanged
    D.txt -> new (created after the baseline)

Expected:

    A.txt -> MODIFIED
    B.txt -> DELETED
    C.txt -> UNCHANGED
    D.txt -> NEW

plus ERROR handling and scan-history persistence.

Each test keeps the SQLite database file outside the monitored directory
(a sibling of it, not inside it) -- exactly as the real application does,
since the database lives in the user's application-data directory rather
than inside a directory it monitors (PROJECT_SPEC.md section 22). Placing
the database inside the monitored directory would make the scan detect the
database's own growth as a MODIFIED file, which is a test-setup mistake,
not scanner behavior.
"""

from __future__ import annotations

import os
import stat

import pytest

from core.baseline import create_baseline, save_baseline
from core.models import ScanStatus
from core.scanner import ScanFileResult, run_scan
from storage import repository
from storage.database import connect


def _write(path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _monitored_and_db(tmp_path):
    """Return (monitored_root, db_path) as siblings under tmp_path."""
    monitored = tmp_path / "monitored"
    monitored.mkdir()
    return monitored, tmp_path / "sentinellite.db"


def test_scan_detects_all_five_statuses(tmp_path):
    """The section 29 / section 33 acceptance scenario."""
    root, db_path = _monitored_and_db(tmp_path)
    _write(root / "A.txt", b"before")
    _write(root / "B.txt", b"will be deleted")
    _write(root / "C.txt", b"stays the same")

    with connect(db_path) as conn:
        baseline, _errors = create_baseline(root)
        baseline = save_baseline(conn, baseline)

        # Modify the filesystem per the scenario.
        (root / "A.txt").write_bytes(b"after")
        (root / "B.txt").unlink()
        (root / "D.txt").write_bytes(b"new file")
        # C.txt is left untouched.

        summary = run_scan(conn, baseline)

    results_by_path = {result.path: result for result in summary.results}
    assert results_by_path["A.txt"].status == ScanStatus.MODIFIED
    assert results_by_path["B.txt"].status == ScanStatus.DELETED
    assert results_by_path["C.txt"].status == ScanStatus.UNCHANGED
    assert results_by_path["D.txt"].status == ScanStatus.NEW

    assert summary.modified_count == 1
    assert summary.new_count == 1
    assert summary.deleted_count == 1
    assert summary.unchanged_count == 1
    assert summary.error_count == 0
    assert summary.has_changes is True


def test_modified_result_carries_both_hashes(tmp_path):
    root, db_path = _monitored_and_db(tmp_path)
    _write(root / "A.txt", b"before")

    with connect(db_path) as conn:
        baseline, _ = create_baseline(root)
        baseline = save_baseline(conn, baseline)
        original_hash = baseline.files[0].sha256

        (root / "A.txt").write_bytes(b"after")
        summary = run_scan(conn, baseline)

    result = next(r for r in summary.results if r.path == "A.txt")
    assert result.status == ScanStatus.MODIFIED
    assert result.baseline_hash == original_hash
    assert result.current_hash != original_hash


def test_new_file_has_no_baseline_hash(tmp_path):
    root, db_path = _monitored_and_db(tmp_path)

    with connect(db_path) as conn:
        baseline, _ = create_baseline(root)
        baseline = save_baseline(conn, baseline)

        (root / "new.txt").write_bytes(b"new")
        summary = run_scan(conn, baseline)

    result = next(r for r in summary.results if r.path == "new.txt")
    assert result.status == ScanStatus.NEW
    assert result.baseline_hash is None
    assert result.current_hash is not None


def test_deleted_file_has_no_current_hash(tmp_path):
    root, db_path = _monitored_and_db(tmp_path)
    _write(root / "gone.txt", b"bye")

    with connect(db_path) as conn:
        baseline, _ = create_baseline(root)
        baseline = save_baseline(conn, baseline)

        (root / "gone.txt").unlink()
        summary = run_scan(conn, baseline)

    result = next(r for r in summary.results if r.path == "gone.txt")
    assert result.status == ScanStatus.DELETED
    assert result.current_hash is None
    assert result.baseline_hash is not None


def test_scan_with_no_changes_reports_unchanged_only(tmp_path):
    root, db_path = _monitored_and_db(tmp_path)
    _write(root / "a.txt", b"one")
    _write(root / "b.txt", b"two")

    with connect(db_path) as conn:
        baseline, _ = create_baseline(root)
        baseline = save_baseline(conn, baseline)

        summary = run_scan(conn, baseline)

    assert summary.unchanged_count == 2
    assert summary.modified_count == summary.new_count == summary.deleted_count == 0
    assert summary.has_changes is False


def test_scan_records_error_for_unreadable_file_without_aborting(tmp_path):
    if os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0):
        pytest.skip("Permission bits are not enforced for root or on Windows.")

    root, db_path = _monitored_and_db(tmp_path)
    _write(root / "readable.txt", b"ok")
    blocked = root / "blocked.txt"
    _write(blocked, b"secret")

    with connect(db_path) as conn:
        # Baseline created while everything is readable.
        baseline, _ = create_baseline(root)
        baseline = save_baseline(conn, baseline)

        blocked.chmod(0)
        try:
            summary = run_scan(conn, baseline)
        finally:
            blocked.chmod(stat.S_IRUSR | stat.S_IWUSR)

    results_by_path = {result.path: result for result in summary.results}
    assert results_by_path["readable.txt"].status == ScanStatus.UNCHANGED
    assert results_by_path["blocked.txt"].status == ScanStatus.ERROR
    assert results_by_path["blocked.txt"].error_message
    assert summary.error_count == 1


def test_scan_against_unsaved_baseline_raises(tmp_path):
    root, db_path = _monitored_and_db(tmp_path)
    baseline, _ = create_baseline(root)

    with connect(db_path) as conn:
        with pytest.raises(ValueError):
            run_scan(conn, baseline)


def test_scan_can_target_a_different_root(tmp_path):
    """``root`` overrides scanning the baseline's own directory -- useful
    for tests and for re-pointing a scan without creating a new baseline."""
    baseline_dir = tmp_path / "baseline_dir"
    other_dir = tmp_path / "other_dir"
    _write(baseline_dir / "a.txt", b"one")
    _write(other_dir / "a.txt", b"different content")
    db_path = tmp_path / "sentinellite.db"

    with connect(db_path) as conn:
        baseline, _ = create_baseline(baseline_dir)
        baseline = save_baseline(conn, baseline)

        summary = run_scan(conn, baseline, root=other_dir)

    result = next(r for r in summary.results if r.path == "a.txt")
    assert result.status == ScanStatus.MODIFIED


def test_scan_is_persisted_and_reloadable(tmp_path):
    root, db_path = _monitored_and_db(tmp_path)
    _write(root / "a.txt", b"one")
    _write(root / "b.txt", b"two")

    with connect(db_path) as conn:
        baseline, _ = create_baseline(root)
        baseline = save_baseline(conn, baseline)

        (root / "b.txt").write_bytes(b"changed")
        (root / "c.txt").write_bytes(b"new")
        summary = run_scan(conn, baseline)

        assert summary.scan_id is not None
        assert repository.get_latest_scan_id(conn) == summary.scan_id
        assert repository.get_latest_scan_id(conn, baseline_id=baseline.baseline_id) == summary.scan_id

        metadata = repository.get_scan_metadata(conn, summary.scan_id)
        assert metadata.baseline_id == baseline.baseline_id
        assert metadata.modified_count == 1
        assert metadata.new_count == 1
        assert metadata.unchanged_count == 1
        assert metadata.deleted_count == 0
        assert metadata.error_count == 0

        stored_results = repository.get_scan_results(conn, summary.scan_id)

    assert {row.path for row in stored_results} == {"a.txt", "b.txt", "c.txt"}
    stored_by_path = {row.path: row for row in stored_results}
    assert stored_by_path["b.txt"].status == ScanStatus.MODIFIED.value
    assert stored_by_path["c.txt"].status == ScanStatus.NEW.value


def test_get_scan_metadata_missing_returns_none(tmp_path):
    db_path = tmp_path / "sentinellite.db"
    with connect(db_path) as conn:
        assert repository.get_scan_metadata(conn, 9999) is None
        assert repository.get_latest_scan_id(conn) is None


def test_multiple_scans_accumulate_history(tmp_path):
    root, db_path = _monitored_and_db(tmp_path)
    _write(root / "a.txt", b"one")

    with connect(db_path) as conn:
        baseline, _ = create_baseline(root)
        baseline = save_baseline(conn, baseline)

        first = run_scan(conn, baseline)
        second = run_scan(conn, baseline)

        assert first.scan_id != second.scan_id
        assert repository.get_latest_scan_id(conn) == second.scan_id


def test_scan_file_result_is_frozen_dataclass():
    result = ScanFileResult(path="a.txt", status=ScanStatus.NEW, current_hash="a" * 64, size=1)
    assert result.baseline_hash is None
    assert result.error_message is None
