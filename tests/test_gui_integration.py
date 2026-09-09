"""Run 5 GUI integration tests (PROJECT_SPEC.md section 30).

Covers the full acceptance-criteria workflow:

    Launch -> Select folder -> Create baseline -> Change a file -> Scan
    -> View MODIFIED result

plus the accidental-replacement confirmation (section 9) and that a
failed scan surfaces a user-friendly error rather than crashing
(section 18). All modal dialogs (folder picker, confirmations,
info/error boxes) are monkeypatched so tests never block on real user
input, and the Tk event loop is pumped manually to let the background
worker thread's ``after`` callbacks run -- consistent with
``tests/test_foundation.py``'s pattern of skipping when no display is
available.
"""

from __future__ import annotations

import time

import pytest

from core.models import ScanStatus


def _require_display():
    tk = pytest.importorskip("tkinter")
    pytest.importorskip("customtkinter")
    try:
        probe = tk.Tk()
        probe.destroy()
    except tk.TclError:
        pytest.skip("No display available for GUI test.")
    return tk


def _pump_until(window, predicate, timeout: float = 5.0) -> None:
    """Run the real Tk event loop until ``predicate()`` is true.

    This must drive an actual ``mainloop()`` rather than polling with
    repeated ``update()`` calls: CPython's tkinter refuses to service a
    background thread's ``after()`` call ("main thread is not in main
    loop") unless the main thread is genuinely inside ``mainloop()``, which
    is exactly the situation SentinelLite's background scan/baseline
    threads run under in the real app (``app.py`` calls
    ``window.mainloop()``). The poll callback itself runs on the GUI
    thread (scheduled via ``after`` from the main thread), so it is safe.
    """
    deadline = time.monotonic() + timeout

    def poll() -> None:
        if predicate() or time.monotonic() > deadline:
            window.quit()
        else:
            window.after(15, poll)

    window.after(15, poll)
    window.mainloop()

    if not predicate():
        raise AssertionError("Timed out waiting for background task to complete.")


@pytest.fixture
def gui_window(tmp_path, monkeypatch):
    _require_display()

    from gui import dialogs
    from gui.main_window import MainWindow

    # Never let a real modal dialog block the test.
    monkeypatch.setattr(dialogs, "show_info", lambda *a, **k: None)
    monkeypatch.setattr(dialogs, "show_error", lambda *a, **k: None)

    window = MainWindow(db_path=tmp_path / "test.db")
    try:
        yield window
    finally:
        window.destroy()


def test_full_workflow_select_baseline_modify_scan(tmp_path, gui_window):
    """The exact Run 5 acceptance scenario, section 30."""
    monitored = tmp_path / "Monitored"
    monitored.mkdir()
    (monitored / "unchanged.txt").write_text("same")
    (monitored / "modified.txt").write_text("before")

    window = gui_window

    # Select folder.
    window._set_directory(monitored)
    assert window._baseline is None
    assert str(window.create_baseline_button.cget("state")) == "normal"
    assert str(window.scan_now_button.cget("state")) == "disabled"

    # Create baseline.
    window._on_create_baseline()
    _pump_until(window, lambda: not window._scan_in_progress)

    assert window._baseline is not None
    assert window._baseline.file_count == 2
    assert str(window.scan_now_button.cget("state")) == "normal"
    assert window.status_label.cget("text") == "Baseline Ready"

    # Change a file, then scan.
    (monitored / "modified.txt").write_text("after")
    (monitored / "new.txt").write_text("new")

    window._on_scan_now()
    _pump_until(window, lambda: not window._scan_in_progress)

    results_by_path = {result.path: result.status for result in window.results_view._results}
    assert results_by_path["unchanged.txt"] == ScanStatus.UNCHANGED
    assert results_by_path["modified.txt"] == ScanStatus.MODIFIED
    assert results_by_path["new.txt"] == ScanStatus.NEW
    assert window.status_label.cget("text") == "⚠ Changes Detected"
    assert window.last_scan_label.cget("text") != "Last scan: never"


def test_scan_with_no_changes_shows_no_changes_detected(tmp_path, gui_window):
    monitored = tmp_path / "Monitored"
    monitored.mkdir()
    (monitored / "a.txt").write_text("same")

    window = gui_window
    window._set_directory(monitored)
    window._on_create_baseline()
    _pump_until(window, lambda: not window._scan_in_progress)

    window._on_scan_now()
    _pump_until(window, lambda: not window._scan_in_progress)

    assert window.status_label.cget("text") == "✓ No Changes Detected"


def test_create_baseline_requires_confirmation_to_replace(tmp_path, gui_window, monkeypatch):
    from gui import dialogs

    monitored = tmp_path / "Monitored"
    monitored.mkdir()
    (monitored / "a.txt").write_text("one")

    window = gui_window
    window._set_directory(monitored)
    window._on_create_baseline()
    _pump_until(window, lambda: not window._scan_in_progress)
    first_baseline_id = window._baseline.baseline_id

    # Decline the replacement warning -- baseline must be unchanged.
    monkeypatch.setattr(dialogs, "confirm_replace_baseline", lambda parent: False)
    window._on_create_baseline()
    assert window._baseline.baseline_id == first_baseline_id

    # Accept -- a new baseline is created.
    monkeypatch.setattr(dialogs, "confirm_replace_baseline", lambda parent: True)
    window._on_create_baseline()
    _pump_until(window, lambda: not window._scan_in_progress)
    assert window._baseline.baseline_id != first_baseline_id


def test_scan_of_removed_directory_reports_error_not_crash(tmp_path, gui_window):
    """PROJECT_SPEC.md section 18: errors must be user-friendly, never crash."""
    monitored = tmp_path / "Monitored"
    monitored.mkdir()
    (monitored / "a.txt").write_text("one")

    window = gui_window
    window._set_directory(monitored)
    window._on_create_baseline()
    _pump_until(window, lambda: not window._scan_in_progress)

    # Remove the monitored directory entirely before scanning.
    import shutil

    shutil.rmtree(monitored)

    window._on_scan_now()
    _pump_until(window, lambda: not window._scan_in_progress)

    assert window.status_label.cget("text") == "✕ Scan Error"


def test_switching_folders_finds_each_folders_own_baseline(tmp_path, gui_window):
    folder_a = tmp_path / "A"
    folder_a.mkdir()
    (folder_a / "a.txt").write_text("one")
    folder_b = tmp_path / "B"
    folder_b.mkdir()
    (folder_b / "b.txt").write_text("two")

    window = gui_window

    window._set_directory(folder_a)
    window._on_create_baseline()
    _pump_until(window, lambda: not window._scan_in_progress)
    baseline_a_id = window._baseline.baseline_id

    window._set_directory(folder_b)
    assert window._baseline is None  # B has no baseline yet
    window._on_create_baseline()
    _pump_until(window, lambda: not window._scan_in_progress)
    baseline_b_id = window._baseline.baseline_id
    assert baseline_b_id != baseline_a_id

    # Switching back to A should find A's baseline again, not B's.
    window._set_directory(folder_a)
    assert window._baseline is not None
    assert window._baseline.baseline_id == baseline_a_id


def test_export_buttons_disabled_until_scan_has_results(tmp_path, gui_window):
    monitored = tmp_path / "Monitored"
    monitored.mkdir()
    (monitored / "a.txt").write_text("one")

    window = gui_window
    assert str(window.results_view.export_csv_button.cget("state")) == "disabled"
    assert str(window.results_view.export_json_button.cget("state")) == "disabled"

    window._set_directory(monitored)
    window._on_create_baseline()
    _pump_until(window, lambda: not window._scan_in_progress)
    # A baseline alone (no scan yet) still has no exportable results.
    assert str(window.results_view.export_csv_button.cget("state")) == "disabled"

    window._on_scan_now()
    _pump_until(window, lambda: not window._scan_in_progress)
    assert str(window.results_view.export_csv_button.cget("state")) == "normal"
    assert str(window.results_view.export_json_button.cget("state")) == "normal"


def test_export_csv_and_json_write_accurate_files(tmp_path, gui_window, monkeypatch):
    """PROJECT_SPEC.md section 15 / Run 6 acceptance: scan -> view results ->
    export CSV -> export JSON, and the exported files contain accurate
    results."""
    import csv
    import json

    monitored = tmp_path / "Monitored"
    monitored.mkdir()
    (monitored / "unchanged.txt").write_text("same")
    (monitored / "modified.txt").write_text("before")

    window = gui_window
    window._set_directory(monitored)
    window._on_create_baseline()
    _pump_until(window, lambda: not window._scan_in_progress)

    (monitored / "modified.txt").write_text("after")
    (monitored / "new.txt").write_text("new")

    window._on_scan_now()
    _pump_until(window, lambda: not window._scan_in_progress)

    assert window._last_scan_id is not None
    scan_id = window._last_scan_id

    csv_destination = tmp_path / "export.csv"
    json_destination = tmp_path / "export.json"
    destinations = iter([str(csv_destination), str(json_destination)])
    from gui import dialogs

    monkeypatch.setattr(dialogs, "choose_save_file", lambda *a, **k: next(destinations))

    window._on_export_csv()
    window._on_export_json()

    assert csv_destination.exists()
    assert json_destination.exists()

    with csv_destination.open(newline="", encoding="utf-8") as handle:
        rows = {row["path"]: row["status"] for row in csv.DictReader(handle)}
    assert rows["unchanged.txt"] == "UNCHANGED"
    assert rows["modified.txt"] == "MODIFIED"
    assert rows["new.txt"] == "NEW"

    with json_destination.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    assert payload["scan_id"] == scan_id
    assert payload["summary"]["modified"] == 1
    assert payload["summary"]["new"] == 1
    assert payload["summary"]["unchanged"] == 1
    results_by_path = {entry["path"]: entry["status"] for entry in payload["results"]}
    assert results_by_path["modified.txt"] == "MODIFIED"


def test_export_cancelled_dialog_writes_nothing(tmp_path, gui_window, monkeypatch):
    monitored = tmp_path / "Monitored"
    monitored.mkdir()
    (monitored / "a.txt").write_text("one")

    window = gui_window
    window._set_directory(monitored)
    window._on_create_baseline()
    _pump_until(window, lambda: not window._scan_in_progress)
    window._on_scan_now()
    _pump_until(window, lambda: not window._scan_in_progress)

    from gui import dialogs

    monkeypatch.setattr(dialogs, "choose_save_file", lambda *a, **k: None)
    # Must not raise even though no destination was chosen.
    window._on_export_csv()
    window._on_export_json()


def test_switching_folders_clears_previous_scans_exportable_results(tmp_path, gui_window):
    folder_a = tmp_path / "A"
    folder_a.mkdir()
    (folder_a / "a.txt").write_text("one")

    window = gui_window
    window._set_directory(folder_a)
    window._on_create_baseline()
    _pump_until(window, lambda: not window._scan_in_progress)
    window._on_scan_now()
    _pump_until(window, lambda: not window._scan_in_progress)
    assert window._last_scan_id is not None

    folder_b = tmp_path / "B"
    folder_b.mkdir()
    window._set_directory(folder_b)
    assert window._last_scan_id is None
    assert str(window.results_view.export_csv_button.cget("state")) == "disabled"


def test_results_view_filter_shows_only_matching_status():
    _require_display()

    from core.scanner import ScanResult
    from gui.results_view import ResultsView

    import tkinter as tk

    root = tk.Tk()
    try:
        view = ResultsView(root)
        view.set_results(
            [
                ScanResult(path="a.txt", status=ScanStatus.MODIFIED, baseline_hash="a", current_hash="b", size=1),
                ScanResult(path="b.txt", status=ScanStatus.NEW, current_hash="c", size=2),
                ScanResult(path="c.txt", status=ScanStatus.UNCHANGED, baseline_hash="d", current_hash="d", size=3),
            ]
        )
        assert len(view.tree.get_children()) == 3

        view._on_filter_changed("Modified")
        assert len(view.tree.get_children()) == 1

        view._on_filter_changed("All")
        assert len(view.tree.get_children()) == 3
    finally:
        root.destroy()
