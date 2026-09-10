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


def test_results_view_export_buttons_enable_with_results_and_invoke_callbacks():
    _require_display()

    from core.scanner import ScanResult
    from gui.results_view import ResultsView

    import tkinter as tk

    root = tk.Tk()
    try:
        csv_calls = []
        json_calls = []
        view = ResultsView(
            root, on_export_csv=lambda: csv_calls.append(True), on_export_json=lambda: json_calls.append(True)
        )

        # No results yet -- export is not meaningful.
        assert str(view.export_csv_button.cget("state")) == "disabled"
        assert str(view.export_json_button.cget("state")) == "disabled"

        view.set_results([ScanResult(path="a.txt", status=ScanStatus.NEW, current_hash="a", size=1)])
        assert str(view.export_csv_button.cget("state")) == "normal"
        assert str(view.export_json_button.cget("state")) == "normal"

        view._handle_export_csv()
        view._handle_export_json()
        assert csv_calls == [True]
        assert json_calls == [True]

        # Clearing the results (e.g. a new folder is selected) disables
        # export again -- there is nothing left to export.
        view.clear()
        assert str(view.export_csv_button.cget("state")) == "disabled"
        assert str(view.export_json_button.cget("state")) == "disabled"
    finally:
        root.destroy()


def test_export_csv_and_json_write_files_for_last_scan(tmp_path, gui_window, monkeypatch):
    """PROJECT_SPEC.md section 31 (Run 6): Scan -> View results -> Export
    CSV -> Export JSON, and the exported files contain accurate results.
    """
    import csv
    import json

    from gui import dialogs

    monitored = tmp_path / "Monitored"
    monitored.mkdir()
    (monitored / "a.txt").write_text("one")

    window = gui_window
    window._set_directory(monitored)

    # Nothing to export before a scan has run.
    assert window._last_scan_id is None
    window._on_export_csv()  # must be a no-op, not raise

    window._on_create_baseline()
    _pump_until(window, lambda: not window._scan_in_progress)

    (monitored / "b.txt").write_text("two")
    window._on_scan_now()
    _pump_until(window, lambda: not window._scan_in_progress)

    assert window._last_scan_id is not None
    assert len(window._last_scan_results) == 2

    csv_destination = tmp_path / "results.csv"
    json_destination = tmp_path / "results.json"
    destinations = iter([str(csv_destination), str(json_destination)])
    monkeypatch.setattr(dialogs, "choose_export_destination", lambda *a, **k: next(destinations))

    window._on_export_csv()
    window._on_export_json()

    with csv_destination.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    assert {row["path"] for row in rows} == {"a.txt", "b.txt"}

    payload = json.loads(json_destination.read_text(encoding="utf-8"))
    assert payload["scan_id"] == window._last_scan_id
    assert payload["root_directory"] == str(window._baseline.root_directory)
    assert {row["path"] for row in payload["results"]} == {"a.txt", "b.txt"}


def test_export_cancelled_dialog_does_not_write_a_file(tmp_path, gui_window, monkeypatch):
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

    monkeypatch.setattr(dialogs, "choose_export_destination", lambda *a, **k: None)
    # Must not raise even though the user cancelled the save dialog.
    window._on_export_csv()
    window._on_export_json()


def test_final_acceptance_section_33(tmp_path, gui_window, monkeypatch):
    """PROJECT_SPEC.md section 33 -- the Final Acceptance Test, performed
    exactly as specified end-to-end through the real GUI (Run 7).

    TestFolder\\
        unchanged.txt
        modified.txt
        deleted.txt

    -> create a baseline -> leave unchanged.txt untouched, modify
    modified.txt, delete deleted.txt, create new.txt -> run a scan ->
    verify each status, the exact summary counts, and that both the CSV
    and JSON exports of the scan are accurate.
    """
    import csv
    import json

    from gui import dialogs

    test_folder = tmp_path / "TestFolder"
    test_folder.mkdir()
    (test_folder / "unchanged.txt").write_text("unchanged content")
    (test_folder / "modified.txt").write_text("original content")
    (test_folder / "deleted.txt").write_text("will be deleted")

    window = gui_window
    window._set_directory(test_folder)
    window._on_create_baseline()
    _pump_until(window, lambda: not window._scan_in_progress)
    assert window._baseline is not None
    assert window._baseline.file_count == 3

    (test_folder / "modified.txt").write_text("changed content")
    (test_folder / "deleted.txt").unlink()
    (test_folder / "new.txt").write_text("brand new file")

    window._on_scan_now()
    _pump_until(window, lambda: not window._scan_in_progress)

    results_by_path = {result.path: result.status for result in window.results_view._results}
    assert results_by_path["unchanged.txt"] == ScanStatus.UNCHANGED
    assert results_by_path["modified.txt"] == ScanStatus.MODIFIED
    assert results_by_path["deleted.txt"] == ScanStatus.DELETED
    assert results_by_path["new.txt"] == ScanStatus.NEW

    summary_text = {
        name: label.cget("text") for name, label in window.results_view._summary_labels.items()
    }
    assert summary_text == {
        "Modified": "Modified: 1",
        "New": "New: 1",
        "Deleted": "Deleted: 1",
        "Unchanged": "Unchanged: 1",
        "Errors": "Errors: 0",
    }
    assert window.status_label.cget("text") == "⚠ Changes Detected"

    csv_destination = tmp_path / "acceptance.csv"
    json_destination = tmp_path / "acceptance.json"
    destinations = iter([str(csv_destination), str(json_destination)])
    monkeypatch.setattr(dialogs, "choose_export_destination", lambda *a, **k: next(destinations))

    window._on_export_csv()
    window._on_export_json()

    with csv_destination.open(newline="", encoding="utf-8") as file:
        csv_rows = {row["path"]: row["status"] for row in csv.DictReader(file)}
    assert csv_rows == {
        "unchanged.txt": "UNCHANGED",
        "modified.txt": "MODIFIED",
        "deleted.txt": "DELETED",
        "new.txt": "NEW",
    }

    payload = json.loads(json_destination.read_text(encoding="utf-8"))
    assert payload["summary"] == {
        "modified": 1,
        "new": 1,
        "deleted": 1,
        "unchanged": 1,
        "errors": 0,
    }
    json_rows = {row["path"]: row["status"] for row in payload["results"]}
    assert json_rows == {
        "unchanged.txt": "UNCHANGED",
        "modified.txt": "MODIFIED",
        "deleted.txt": "DELETED",
        "new.txt": "NEW",
    }
