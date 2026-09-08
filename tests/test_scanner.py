"""Tests for core.scanner (PROJECT_SPEC.md section 10 - Scan Algorithm,
section 19 - Scanner testing, section 29 - Run 4).

Covers the exact five-status scenario from section 29 / section 33 (Final
Acceptance Test):

    A.txt -> modified
    B.txt -> deleted
    C.txt -> unchanged
    D.txt -> new

plus ERROR handling and that a completed scan is persisted and reloadable
via storage.repository.
"""

from __future__ import annotations

import pytest

from core.baseline import Baseline, create_baseline, save_baseline
from core.models import FileError, FileRecord, ScanStatus
from core.scanner import ScanSummary, compare_to_baseline, run_scan
from storage import repository
from storage.database import connect


def _write(path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _baseline_with(*records: FileRecord) -> Baseline:
    return Baseline(
        root_directory="/tmp/monitored",
        created_at="2026-01-01T00:00:00+00:00",
        application_version="0.1.0",
        files=tuple(records),
        baseline_id=1,
    )


# ---------------------------------------------------------------------------
# compare_to_baseline: pure comparison logic
# ---------------------------------------------------------------------------


def test_five_status_scenario_from_spec_section_29():
    """A = modified, B = deleted, C = unchanged, D = new (section 29/33)."""
    baseline = _baseline_with(
        FileRecord(path="A.txt", sha256="a" * 64, size=1, modified_time=0.0),
        FileRecord(path="B.txt", sha256="b" * 64, size=1, modified_time=0.0),
        FileRecord(path="C.txt", sha256="c" * 64, size=1, modified_time=0.0),
    )
    current_records = [
        FileRecord(path="A.txt", sha256="a-modified" * 8, size=2, modified_time=1.0),
        FileRecord(path="C.txt", sha256="c" * 64, size=1, modified_time=0.0),
        FileRecord(path="D.txt", sha256="d" * 64, size=1, modified_time=1.0),
    ]

    results, summary = compare_to_baseline(baseline, current_records, [])

    by_path = {result.path: result for result in results}
    assert by_path["A.txt"].status == ScanStatus.MODIFIED
    assert by_path["B.txt"].status == ScanStatus.DELETED
    assert by_path["C.txt"].status == ScanStatus.UNCHANGED
    assert by_path["D.txt"].status == ScanStatus.NEW

    assert summary == ScanSummary(modified=1, new=1, deleted=1, unchanged=1, errors=0)
    assert summary.total == 4
    # Results are sorted by path for stable display.
    assert [result.path for result in results] == ["A.txt", "B.txt", "C.txt", "D.txt"]


def test_new_file_has_no_baseline_hash():
    baseline = _baseline_with()
    current_records = [FileRecord(path="new.txt", sha256="d" * 64, size=1, modified_time=1.0)]

    results, summary = compare_to_baseline(baseline, current_records, [])

    assert len(results) == 1
    result = results[0]
    assert result.status == ScanStatus.NEW
    assert result.baseline_hash is None
    assert result.current_hash == "d" * 64
    assert summary.new == 1


def test_deleted_file_has_no_current_hash():
    baseline = _baseline_with(FileRecord(path="gone.txt", sha256="b" * 64, size=1, modified_time=0.0))

    results, summary = compare_to_baseline(baseline, [], [])

    assert len(results) == 1
    result = results[0]
    assert result.status == ScanStatus.DELETED
    assert result.baseline_hash == "b" * 64
    assert result.current_hash is None
    assert summary.deleted == 1


def test_unchanged_file_matches_hash():
    baseline = _baseline_with(FileRecord(path="same.txt", sha256="c" * 64, size=1, modified_time=0.0))
    current_records = [FileRecord(path="same.txt", sha256="c" * 64, size=1, modified_time=0.0)]

    results, summary = compare_to_baseline(baseline, current_records, [])

    assert results[0].status == ScanStatus.UNCHANGED
    assert summary.unchanged == 1


def test_error_file_reported_instead_of_new_or_deleted():
    """A file that failed to hash this scan is ERROR, not NEW/DELETED,
    even if it existed in (or is absent from) the baseline."""
    baseline = _baseline_with(FileRecord(path="in_baseline.txt", sha256="a" * 64, size=1, modified_time=0.0))

    results, summary = compare_to_baseline(
        baseline,
        [],
        [
            FileError(path="in_baseline.txt", message="Permission denied"),
            FileError(path="never_seen.txt", message="Permission denied"),
        ],
    )

    by_path = {result.path: result for result in results}
    assert by_path["in_baseline.txt"].status == ScanStatus.ERROR
    assert by_path["in_baseline.txt"].baseline_hash == "a" * 64
    assert by_path["in_baseline.txt"].error_message == "Permission denied"
    assert by_path["never_seen.txt"].status == ScanStatus.ERROR
    assert by_path["never_seen.txt"].baseline_hash is None
    assert summary.errors == 2
    assert summary.deleted == 0


def test_empty_baseline_and_empty_current_produces_no_results():
    results, summary = compare_to_baseline(_baseline_with(), [], [])
    assert results == []
    assert summary == ScanSummary()
    assert summary.total == 0


# ---------------------------------------------------------------------------
# run_scan: end-to-end orchestration + persistence
# ---------------------------------------------------------------------------


def test_run_scan_end_to_end_persists_and_matches_final_acceptance_test(tmp_path):
    """The exact scenario from PROJECT_SPEC.md section 33 (Final Acceptance Test)."""
    monitored = tmp_path / "TestFolder"
    _write(monitored / "unchanged.txt", b"same")
    _write(monitored / "modified.txt", b"before")
    _write(monitored / "deleted.txt", b"will be removed")
    db_path = tmp_path / "sentinellite.db"

    baseline, _errors = create_baseline(monitored)
    with connect(db_path) as conn:
        baseline = save_baseline(conn, baseline)

    # Apply the section 33 changes.
    (monitored / "modified.txt").write_bytes(b"after")
    (monitored / "deleted.txt").unlink()
    _write(monitored / "new.txt", b"just added")

    with connect(db_path) as conn:
        scan_id, results, summary = run_scan(conn, monitored, baseline)

        # Persisted scan is independently reloadable.
        metadata = repository.get_scan_metadata(conn, scan_id)
        stored_results = repository.get_scan_results(conn, scan_id)

    assert summary == ScanSummary(modified=1, new=1, deleted=1, unchanged=1, errors=0)

    by_path = {result.path: result.status for result in results}
    assert by_path == {
        "unchanged.txt": ScanStatus.UNCHANGED,
        "modified.txt": ScanStatus.MODIFIED,
        "deleted.txt": ScanStatus.DELETED,
        "new.txt": ScanStatus.NEW,
    }

    assert metadata is not None
    assert metadata.baseline_id == baseline.baseline_id
    assert metadata.modified_count == 1
    assert metadata.new_count == 1
    assert metadata.deleted_count == 1
    assert metadata.unchanged_count == 1
    assert metadata.error_count == 0
    assert metadata.completed_at is not None

    assert {row.relative_path: row.status for row in stored_results} == {
        "unchanged.txt": "UNCHANGED",
        "modified.txt": "MODIFIED",
        "deleted.txt": "DELETED",
        "new.txt": "NEW",
    }


def test_run_scan_against_unsaved_baseline_raises(tmp_path):
    monitored = tmp_path / "Monitored"
    _write(monitored / "a.txt", b"one")
    baseline, _errors = create_baseline(monitored)  # baseline_id is None
    db_path = tmp_path / "sentinellite.db"

    with connect(db_path) as conn:
        with pytest.raises(ValueError):
            run_scan(conn, monitored, baseline)


def test_run_scan_multiple_scans_are_independently_stored(tmp_path):
    monitored = tmp_path / "Monitored"
    _write(monitored / "a.txt", b"one")
    db_path = tmp_path / "sentinellite.db"

    baseline, _errors = create_baseline(monitored)
    with connect(db_path) as conn:
        baseline = save_baseline(conn, baseline)
        first_scan_id, _, first_summary = run_scan(conn, monitored, baseline)

        _write(monitored / "b.txt", b"two")
        second_scan_id, _, second_summary = run_scan(conn, monitored, baseline)

        assert first_scan_id != second_scan_id
        assert first_summary == ScanSummary(unchanged=1)
        assert second_summary == ScanSummary(unchanged=1, new=1)

        # The earlier scan's persisted results are unaffected by the later scan.
        assert len(repository.get_scan_results(conn, first_scan_id)) == 1
        assert len(repository.get_scan_results(conn, second_scan_id)) == 2
