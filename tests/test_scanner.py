"""Tests for core.scanner (PROJECT_SPEC.md section 19 - Scanner,
section 29 - Run 4).

Covers the exact acceptance scenario from section 29:

    A = modified, B = deleted, C = unchanged, D = new
    -> A: MODIFIED, B: DELETED, C: UNCHANGED, D: NEW

plus ERROR handling and scan-history persistence via storage.repository.
"""

from __future__ import annotations

import os
import stat

import pytest

from core.baseline import create_baseline, save_baseline
from core.models import FileError, FileRecord, ScanStatus
from core.scanner import (
    ScanResult,
    ScanSummary,
    compare_to_baseline,
    get_scan_results,
    list_scans,
    run_scan,
    save_scan,
)
from storage.database import connect


def _write(path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _record(path: str, content: bytes) -> FileRecord:
    import hashlib

    return FileRecord(path=path, sha256=hashlib.sha256(content).hexdigest(), size=len(content), modified_time=0.0)


def _by_path(results: list[ScanResult]) -> dict[str, ScanResult]:
    return {result.path: result for result in results}


def test_section_29_acceptance_scenario(tmp_path):
    """A=modified, B=deleted, C=unchanged, D=new -> exact statuses from the spec."""
    _write(tmp_path / "A.txt", b"original")
    _write(tmp_path / "B.txt", b"will be deleted")
    _write(tmp_path / "C.txt", b"never changes")

    baseline, errors = create_baseline(tmp_path)
    assert errors == []

    # Apply the scenario's filesystem changes.
    (tmp_path / "A.txt").write_bytes(b"changed")
    (tmp_path / "B.txt").unlink()
    _write(tmp_path / "D.txt", b"brand new")
    # C.txt is left untouched.

    results = run_scan(baseline)
    by_path = _by_path(results)

    assert by_path["A.txt"].status == ScanStatus.MODIFIED
    assert by_path["B.txt"].status == ScanStatus.DELETED
    assert by_path["C.txt"].status == ScanStatus.UNCHANGED
    assert by_path["D.txt"].status == ScanStatus.NEW
    assert len(results) == 4


def test_final_acceptance_test_section_33(tmp_path):
    """The exact end-to-end scenario from PROJECT_SPEC.md section 33."""
    _write(tmp_path / "unchanged.txt", b"stays the same")
    _write(tmp_path / "modified.txt", b"before")
    _write(tmp_path / "deleted.txt", b"goes away")

    baseline, _errors = create_baseline(tmp_path)

    (tmp_path / "modified.txt").write_bytes(b"after")
    (tmp_path / "deleted.txt").unlink()
    _write(tmp_path / "new.txt", b"just added")

    results = run_scan(baseline)
    summary = ScanSummary.from_results(results)

    assert summary.modified == 1
    assert summary.new == 1
    assert summary.deleted == 1
    assert summary.unchanged == 1
    assert summary.errors == 0

    by_path = _by_path(results)
    assert by_path["unchanged.txt"].status == ScanStatus.UNCHANGED
    assert by_path["modified.txt"].status == ScanStatus.MODIFIED
    assert by_path["deleted.txt"].status == ScanStatus.DELETED
    assert by_path["new.txt"].status == ScanStatus.NEW


def test_compare_to_baseline_is_pure_and_covers_all_statuses():
    """Unit-level check of the comparison logic without touching disk."""
    baseline = type(
        "B",
        (),
        {
            "files": (
                _record("modified.txt", b"old"),
                _record("deleted.txt", b"gone"),
                _record("unchanged.txt", b"same"),
            )
        },
    )()

    current_records = [
        _record("modified.txt", b"new"),
        _record("unchanged.txt", b"same"),
        _record("new.txt", b"brand new"),
    ]

    results = compare_to_baseline(baseline, current_records)
    by_path = _by_path(results)

    assert by_path["modified.txt"].status == ScanStatus.MODIFIED
    assert by_path["modified.txt"].baseline_hash != by_path["modified.txt"].current_hash
    assert by_path["deleted.txt"].status == ScanStatus.DELETED
    assert by_path["deleted.txt"].current_hash is None
    assert by_path["unchanged.txt"].status == ScanStatus.UNCHANGED
    assert by_path["new.txt"].status == ScanStatus.NEW
    assert by_path["new.txt"].baseline_hash is None


def test_compare_to_baseline_reports_unreadable_files_as_error():
    baseline = type("B", (), {"files": (_record("locked.txt", b"secret"),)})()

    results = compare_to_baseline(
        baseline,
        current_records=[],
        current_errors=[FileError(path="locked.txt", message="Permission denied")],
    )

    assert len(results) == 1
    assert results[0].status == ScanStatus.ERROR
    assert results[0].error_message == "Permission denied"
    # The baseline hash is still surfaced for context; there is no current hash.
    assert results[0].baseline_hash == _record("locked.txt", b"secret").sha256
    assert results[0].current_hash is None


def test_run_scan_continues_after_unreadable_file(tmp_path):
    if os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0):
        pytest.skip("Permission bits are not enforced for root or on Windows.")

    _write(tmp_path / "readable.txt", b"ok")
    blocked = tmp_path / "blocked.txt"
    _write(blocked, b"secret")

    baseline, _errors = create_baseline(tmp_path)
    blocked.chmod(0)
    try:
        results = run_scan(baseline)
    finally:
        blocked.chmod(stat.S_IRUSR | stat.S_IWUSR)

    by_path = _by_path(results)
    assert by_path["readable.txt"].status == ScanStatus.UNCHANGED
    assert by_path["blocked.txt"].status == ScanStatus.ERROR
    assert by_path["blocked.txt"].error_message


def test_scan_summary_from_results_counts_each_status():
    results = [
        ScanResult(path="a", status=ScanStatus.MODIFIED),
        ScanResult(path="b", status=ScanStatus.NEW),
        ScanResult(path="c", status=ScanStatus.DELETED),
        ScanResult(path="d", status=ScanStatus.UNCHANGED),
        ScanResult(path="e", status=ScanStatus.UNCHANGED),
        ScanResult(path="f", status=ScanStatus.ERROR),
    ]
    summary = ScanSummary.from_results(results)

    assert summary.modified == 1
    assert summary.new == 1
    assert summary.deleted == 1
    assert summary.unchanged == 2
    assert summary.errors == 1
    assert summary.total == 6


def test_save_and_load_scan_round_trip(tmp_path):
    monitored = tmp_path / "monitored"
    _write(monitored / "a.txt", b"one")
    _write(monitored / "b.txt", b"two")
    db_path = tmp_path / "sentinellite.db"

    baseline, _errors = create_baseline(monitored)
    with connect(db_path) as conn:
        saved_baseline = save_baseline(conn, baseline)

    (monitored / "b.txt").write_bytes(b"two-modified")
    _write(monitored / "c.txt", b"three")

    results = run_scan(baseline)

    with connect(db_path) as conn:
        scan_id = save_scan(
            conn,
            baseline_id=saved_baseline.baseline_id,
            started_at="2026-09-08T00:00:00+00:00",
            results=results,
        )

        loaded_results = get_scan_results(conn, scan_id)
        history = list_scans(conn, baseline_id=saved_baseline.baseline_id)

    assert sorted(loaded_results, key=lambda r: r.path) == sorted(results, key=lambda r: r.path)
    assert len(history) == 1
    assert history[0].scan_id == scan_id
    assert history[0].baseline_id == saved_baseline.baseline_id
    assert history[0].modified_count == 1
    assert history[0].new_count == 1
    assert history[0].unchanged_count == 1
    assert history[0].deleted_count == 0
    assert history[0].error_count == 0


def test_list_scans_orders_most_recent_first(tmp_path):
    _write(tmp_path / "a.txt", b"one")
    db_path = tmp_path / "sentinellite.db"

    baseline, _errors = create_baseline(tmp_path)
    with connect(db_path) as conn:
        saved_baseline = save_baseline(conn, baseline)

        first_id = save_scan(
            conn, baseline_id=saved_baseline.baseline_id, started_at="2026-09-01T00:00:00+00:00", results=[]
        )
        second_id = save_scan(
            conn, baseline_id=saved_baseline.baseline_id, started_at="2026-09-02T00:00:00+00:00", results=[]
        )

        history = list_scans(conn, baseline_id=saved_baseline.baseline_id)

    assert [scan.scan_id for scan in history] == [second_id, first_id]


def test_run_scan_missing_directory_raises(tmp_path):
    baseline, _errors = create_baseline(tmp_path)
    missing_root = tmp_path / "does_not_exist_anymore"
    # Construct a baseline pointing at a directory that no longer exists.
    from dataclasses import replace

    stale_baseline = replace(baseline, root_directory=str(missing_root))

    with pytest.raises(NotADirectoryError):
        run_scan(stale_baseline)
