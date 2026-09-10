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


# ---------------------------------------------------------------------------
# Run 6 - Reporting and scan history (PROJECT_SPEC.md sections 15, 31)
# ---------------------------------------------------------------------------


def test_export_buttons_disabled_until_results_exist(tmp_path, gui_window):
    window = gui_window
    assert str(window.results_view.export_csv_button.cget("state")) == "disabled"
    assert str(window.results_view.export_json_button.cget("state")) == "disabled"

    monitored = tmp_path / "Monitored"
    monitored.mkdir()
    (monitored / "a.txt").write_text("one")

    window._set_directory(monitored)
    window._on_create_baseline()
    _pump_until(window, lambda: not window._scan_in_progress)
    window._on_scan_now()
    _pump_until(window, lambda: not window._scan_in_progress)

    assert str(window.results_view.export_csv_button.cget("state")) == "normal"
    assert str(window.results_view.export_json_button.cget("state")) == "normal"


def test_export_csv_and_json_write_expected_files(tmp_path, gui_window, monkeypatch):
    from gui import dialogs

    monitored = tmp_path / "Monitored"
    monitored.mkdir()
    (monitored / "a.txt").write_text("one")

    window = gui_window
    window._set_directory(monitored)
    window._on_create_baseline()
    _pump_until(window, lambda: not window._scan_in_progress)

    (monitored / "b.txt").write_text("new")
    window._on_scan_now()
    _pump_until(window, lambda: not window._scan_in_progress)

    csv_path = tmp_path / "exports" / "out.csv"
    json_path = tmp_path / "exports" / "out.json"
    destinations = iter([str(csv_path), str(json_path)])
    monkeypatch.setattr(dialogs, "choose_export_destination", lambda *a, **k: next(destinations))

    window.results_view._on_export_csv()
    window.results_view._on_export_json()

    assert csv_path.exists()
    assert json_path.exists()

    import csv as csv_module

    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv_module.reader(handle))
    assert rows[0] == ["status", "path", "baseline_hash", "current_hash", "size", "timestamp"]
    assert len(rows) == 1 + len(window.results_view._results)

    import json as json_module

    payload = json_module.loads(json_path.read_text())
    assert payload["root_directory"] == window._baseline.root_directory
    assert payload["scan_id"] == window.results_view._scan_id
    assert len(payload["results"]) == len(window.results_view._results)


def test_export_failure_shows_friendly_error_not_crash(tmp_path, gui_window, monkeypatch):
    """PROJECT_SPEC.md section 18: export failures must not crash the app."""
    from gui import dialogs

    monitored = tmp_path / "Monitored"
    monitored.mkdir()
    (monitored / "a.txt").write_text("one")

    window = gui_window
    window._set_directory(monitored)
    window._on_create_baseline()
    _pump_until(window, lambda: not window._scan_in_progress)
    window._on_scan_now()
    _pump_until(window, lambda: not window._scan_in_progress)

    # A destination inside a file (not a directory) cannot be written to.
    blocked_parent = tmp_path / "not_a_directory"
    blocked_parent.write_text("occupied")
    bad_destination = str(blocked_parent / "out.csv")
    monkeypatch.setattr(dialogs, "choose_export_destination", lambda *a, **k: bad_destination)

    errors = []
    monkeypatch.setattr(dialogs, "show_error", lambda *a, **k: errors.append(a))

    window.results_view._on_export_csv()  # must not raise

    assert len(errors) == 1


def test_scan_history_lists_scans_and_reloads_selected(tmp_path, gui_window):
    monitored = tmp_path / "Monitored"
    monitored.mkdir()
    (monitored / "a.txt").write_text("one")

    window = gui_window
    window._set_directory(monitored)
    window._on_create_baseline()
    _pump_until(window, lambda: not window._scan_in_progress)
    assert str(window.scan_history_button.cget("state")) == "normal"

    window._on_scan_now()
    _pump_until(window, lambda: not window._scan_in_progress)
    first_scan_id = window.results_view._scan_id

    (monitored / "b.txt").write_text("two")
    window._on_scan_now()
    _pump_until(window, lambda: not window._scan_in_progress)
    second_scan_id = window.results_view._scan_id
    assert second_scan_id != first_scan_id

    from core.scanner import list_scans

    scans = list_scans(window._connection, baseline_id=window._baseline.baseline_id)
    assert len(scans) == 2
    assert {scan.scan_id for scan in scans} == {first_scan_id, second_scan_id}

    # Reload the first scan, as the history dialog's "View Selected" would.
    first_metadata = next(scan for scan in scans if scan.scan_id == first_scan_id)
    window._on_history_scan_selected(first_metadata)

    assert window.results_view._scan_id == first_scan_id
    assert "(from history)" in window.last_scan_label.cget("text")
    assert window.status_label.cget("text") == "Viewing scan history"


def test_scan_history_with_no_scans_shows_info_not_empty_dialog(tmp_path, gui_window, monkeypatch):
    from gui import dialogs

    monitored = tmp_path / "Monitored"
    monitored.mkdir()
    (monitored / "a.txt").write_text("one")

    window = gui_window
    window._set_directory(monitored)
    window._on_create_baseline()
    _pump_until(window, lambda: not window._scan_in_progress)

    infos = []
    monkeypatch.setattr(dialogs, "show_info", lambda *a, **k: infos.append(a))

    window._on_view_scan_history()

    assert len(infos) == 1


def test_scan_history_dialog_selects_and_invokes_callback():
    _require_display()

    from core.scanner import ScanMetadata
    from gui.history_dialog import ScanHistoryDialog

    import tkinter as tk

    root = tk.Tk()
    try:
        scans = [
            ScanMetadata(
                scan_id=1,
                baseline_id=1,
                started_at="2026-09-08T00:00:00+00:00",
                completed_at="2026-09-08T00:05:00+00:00",
                modified_count=1,
                new_count=0,
                deleted_count=0,
                unchanged_count=2,
                error_count=0,
            ),
        ]
        selected: list = []
        dialog = ScanHistoryDialog(root, scans, on_select=selected.append)
        dialog.update()
        dialog._select_current()

        assert selected == scans
    finally:
        root.destroy()
