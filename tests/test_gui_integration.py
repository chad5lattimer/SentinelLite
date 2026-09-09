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


def test_export_csv_and_json_write_current_results(tmp_path, gui_window, monkeypatch):
    """Run 6 acceptance criteria (section 31): scan -> export CSV -> export JSON."""
    import json

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

    csv_path = tmp_path / "out.csv"
    monkeypatch.setattr(dialogs, "choose_export_destination", lambda *a, **k: str(csv_path))
    window._on_export_csv()
    assert csv_path.exists()
    assert csv_path.read_text().splitlines()[0] == (
        "status,path,baseline_hash,current_hash,size,timestamp"
    )

    json_path = tmp_path / "out.json"
    monkeypatch.setattr(dialogs, "choose_export_destination", lambda *a, **k: str(json_path))
    window._on_export_json()
    assert json_path.exists()
    payload = json.loads(json_path.read_text())
    assert payload["scan_id"] == window._last_scan_id
    assert payload["root_directory"] == str(monitored.resolve())
    assert len(payload["results"]) == 1


def test_export_with_no_results_shows_info_not_dialog(tmp_path, gui_window, monkeypatch):
    from gui import dialogs

    monitored = tmp_path / "Monitored"
    monitored.mkdir()

    window = gui_window
    window._set_directory(monitored)

    called = []
    monkeypatch.setattr(dialogs, "choose_export_destination", lambda *a, **k: called.append(1))
    window._on_export_csv()
    assert called == []  # never prompted for a destination -- nothing to export yet


def test_view_history_loads_a_past_scan_into_the_results_view(tmp_path, gui_window, monkeypatch):
    """Run 6 acceptance criteria (section 31): a scan-history UI exists."""
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
    first_scan_id = window._last_scan_id

    # A second scan with no changes -- history should offer both.
    window._on_scan_now()
    _pump_until(window, lambda: not window._scan_in_progress)

    from storage.repository import list_scans as list_scans_direct

    scans = list_scans_direct(window._connection, baseline_id=window._baseline.baseline_id)
    assert len(scans) == 2

    monkeypatch.setattr(dialogs, "show_scan_history", lambda parent, scans: scans[-1])
    window._on_view_history()

    assert window._last_scan_id == first_scan_id
    assert len(window.results_view.results) == 1
    assert "Viewing scan history" in window.status_label.cget("text")


def test_view_history_with_no_scans_shows_info(tmp_path, gui_window, monkeypatch):
    from gui import dialogs

    monitored = tmp_path / "Monitored"
    monitored.mkdir()
    (monitored / "a.txt").write_text("one")

    window = gui_window
    window._set_directory(monitored)
    window._on_create_baseline()
    _pump_until(window, lambda: not window._scan_in_progress)

    called = []
    monkeypatch.setattr(dialogs, "show_scan_history", lambda *a, **k: called.append(1))
    window._on_view_history()
    assert called == []  # never opened the history browser -- there is no history yet


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
