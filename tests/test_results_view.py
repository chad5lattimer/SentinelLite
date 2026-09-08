"""Tests for the pure result-filtering logic in gui.results_view.

PROJECT_SPEC.md section 12 requires the results table to be filterable by
All / Modified / New / Deleted / Unchanged / Errors. ``filter_results`` is
kept as a plain function (no widget dependency) specifically so this
behavior is unit-testable; it still requires tkinter to *import* the
module (customtkinter needs it), so this file is skipped in the same
tkinter-less environments as the other GUI tests.
"""

from __future__ import annotations

import pytest

pytest.importorskip("tkinter")

from core.models import ScanStatus  # noqa: E402
from core.scanner import ScanResult  # noqa: E402
from gui.results_view import FILTER_OPTIONS, filter_results  # noqa: E402


def _make_results() -> list[ScanResult]:
    return [
        ScanResult(path="modified.txt", status=ScanStatus.MODIFIED, baseline_hash="a", current_hash="b"),
        ScanResult(path="new.txt", status=ScanStatus.NEW, current_hash="c"),
        ScanResult(path="deleted.txt", status=ScanStatus.DELETED, baseline_hash="d"),
        ScanResult(path="unchanged.txt", status=ScanStatus.UNCHANGED, baseline_hash="e", current_hash="e"),
        ScanResult(path="broken.txt", status=ScanStatus.ERROR, error_message="Permission denied"),
    ]


def test_filter_all_returns_every_result():
    results = _make_results()
    assert filter_results(results, "All") == results


@pytest.mark.parametrize(
    "filter_name,expected_status",
    [
        ("Modified", ScanStatus.MODIFIED),
        ("New", ScanStatus.NEW),
        ("Deleted", ScanStatus.DELETED),
        ("Unchanged", ScanStatus.UNCHANGED),
        ("Errors", ScanStatus.ERROR),
    ],
)
def test_filter_by_status_returns_only_matching_results(filter_name, expected_status):
    results = _make_results()
    filtered = filter_results(results, filter_name)
    assert filtered
    assert all(result.status == expected_status for result in filtered)


def test_filter_options_cover_every_scan_status():
    assert FILTER_OPTIONS[0] == "All"
    assert set(FILTER_OPTIONS[1:]) == {"Modified", "New", "Deleted", "Unchanged", "Errors"}


def test_unknown_filter_raises():
    with pytest.raises(ValueError):
        filter_results(_make_results(), "Bogus")
