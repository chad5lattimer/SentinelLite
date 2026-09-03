"""Run 2 tests: core data models (PROJECT_SPEC.md section 6)."""

from __future__ import annotations

from core.models import FileAccessError, FileRecord, ScanStatus


def test_file_record_fields():
    record = FileRecord(path="documents/example.txt", sha256="abc123", size=1024, modified_time=1787700000.0)

    assert record.path == "documents/example.txt"
    assert record.sha256 == "abc123"
    assert record.size == 1024
    assert record.modified_time == 1787700000.0


def test_file_record_is_immutable():
    record = FileRecord(path="a.txt", sha256="abc", size=1, modified_time=0.0)

    try:
        record.path = "b.txt"  # type: ignore[misc]
    except Exception:
        pass
    else:
        raise AssertionError("FileRecord should be frozen/immutable.")


def test_file_access_error_fields():
    error = FileAccessError(path="a.txt", message="Permission denied")

    assert error.path == "a.txt"
    assert error.message == "Permission denied"


def test_scan_status_values():
    assert {status.value for status in ScanStatus} == {
        "NEW",
        "MODIFIED",
        "DELETED",
        "UNCHANGED",
        "ERROR",
    }
