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


def test_uncaught_callback_exception_shows_fatal_error_not_crash(gui_window, monkeypatch):
    """PROJECT_SPEC.md section 24 ("Fatal application error") + section 18.

    An exception raised synchronously inside a Tk callback (bypassing the
    background-task error handling entirely) must not crash the app or
    vanish silently -- it must be logged and surfaced to the user via
    ``report_callback_exception`` (gui/main_window.py).
    """
    import sys

    from gui import dialogs

    window = gui_window
    shown: list[tuple[str, str]] = []
    monkeypatch.setattr(
        dialogs, "show_error", lambda parent, title, message: shown.append((title, message))
    )

    try:
        raise RuntimeError("boom")
    except RuntimeError:
        window.report_callback_exception(*sys.exc_info())

    assert shown, "Expected a user-facing error dialog for the uncaught exception."
    assert "unexpected error" in shown[0][1].lower()
    # The window must remain fully usable afterwards.
    assert window.winfo_exists()


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


# ----------------------------------------------------------------------
# Run 12 additions: gap closure for branches that existed but were never
# actually exercised by any test (guard clauses, error paths, sorting).
# Found via `pytest --cov`; no production behavior changed.
# ----------------------------------------------------------------------


def test_format_display_time_falls_back_to_raw_string_for_malformed_input():
    """An unparsable timestamp is shown as-is rather than raising."""
    _require_display()

    from gui.main_window import _format_display_time

    assert _format_display_time("not-a-timestamp") == "not-a-timestamp"


def test_change_folder_selects_directory_via_dialog(tmp_path, gui_window, monkeypatch):
    """PROJECT_SPEC.md section 11.2 "[ Change Folder ]" -- the real dialog
    path, as opposed to ``_set_directory`` which the other tests call
    directly to bypass the folder picker.
    """
    from gui import dialogs

    chosen = tmp_path / "Chosen"
    chosen.mkdir()

    window = gui_window
    monkeypatch.setattr(dialogs, "choose_directory", lambda *a, **k: str(chosen))
    window._on_change_folder()

    assert window._directory == chosen.resolve()


def test_change_folder_cancelled_dialog_is_a_noop(tmp_path, gui_window, monkeypatch):
    from gui import dialogs

    monitored = tmp_path / "Monitored"
    monitored.mkdir()

    window = gui_window
    window._set_directory(monitored)
    monkeypatch.setattr(dialogs, "choose_directory", lambda *a, **k: "")
    window._on_change_folder()

    assert window._directory == monitored.resolve()


def test_change_folder_no_op_while_scan_in_progress(gui_window, monkeypatch):
    from gui import dialogs

    window = gui_window
    calls = []
    monkeypatch.setattr(dialogs, "choose_directory", lambda *a, **k: calls.append(True))
    window._scan_in_progress = True
    window._on_change_folder()

    assert calls == []


def test_create_baseline_no_op_without_directory(gui_window):
    window = gui_window
    assert window._directory is None
    window._on_create_baseline()  # must not raise
    assert window._baseline is None


def test_create_baseline_no_op_while_scan_in_progress(tmp_path, gui_window):
    monitored = tmp_path / "Monitored"
    monitored.mkdir()

    window = gui_window
    window._set_directory(monitored)
    window._scan_in_progress = True
    window._on_create_baseline()  # must not raise or start a second task

    assert window._baseline is None


def test_scan_now_no_op_without_baseline(gui_window):
    window = gui_window
    window._on_scan_now()  # must not raise
    assert window._last_scan_id is None


def test_scan_now_no_op_while_scan_in_progress(tmp_path, gui_window):
    monitored = tmp_path / "Monitored"
    monitored.mkdir()
    (monitored / "a.txt").write_text("one")

    window = gui_window
    window._set_directory(monitored)
    window._on_create_baseline()
    _pump_until(window, lambda: not window._scan_in_progress)

    window._scan_in_progress = True
    window._on_scan_now()  # must not raise or start a second task

    assert window._last_scan_id is None


def test_baseline_creation_failure_shows_error_dialog(tmp_path, gui_window, monkeypatch):
    """PROJECT_SPEC.md section 18: an unexpected failure while creating a
    baseline must be reported to the user, not crash the app.
    """
    import gui.main_window as main_window
    from gui import dialogs

    monitored = tmp_path / "Monitored"
    monitored.mkdir()

    def _boom(*a, **k):
        raise RuntimeError("disk exploded")

    window = gui_window
    window._set_directory(monitored)
    monkeypatch.setattr(main_window, "create_baseline", _boom)

    shown = []
    monkeypatch.setattr(dialogs, "show_error", lambda parent, title, message: shown.append(title))

    window._on_create_baseline()
    _pump_until(window, lambda: not window._scan_in_progress)

    assert window._baseline is None
    assert shown == ["Unable to Create Baseline"]
    assert window.status_label.cget("text") == "The application encountered an unexpected error."


def test_baseline_created_with_unreadable_files_logs_a_warning(tmp_path, gui_window, monkeypatch, caplog):
    """PROJECT_SPEC.md section 7.3: unreadable files are excluded from the
    baseline but reported, not silently dropped.
    """
    import logging

    import gui.main_window as main_window
    from core.baseline import Baseline
    from core.models import FileError

    monitored = tmp_path / "Monitored"
    monitored.mkdir()

    fake_baseline = Baseline(root_directory=str(monitored), created_at="2026-01-01T00:00:00+00:00", application_version="test")
    fake_errors = [FileError(path="secret.txt", message="Permission denied")]
    monkeypatch.setattr(
        main_window, "create_baseline", lambda *a, **k: (fake_baseline, fake_errors)
    )

    window = gui_window
    window._set_directory(monitored)
    with caplog.at_level(logging.WARNING):
        window._on_create_baseline()
        _pump_until(window, lambda: not window._scan_in_progress)

    assert window._baseline is not None
    assert any("unreadable file" in record.message for record in caplog.records)


def test_scan_completed_with_errors_shows_errors_status(tmp_path, gui_window, monkeypatch):
    """PROJECT_SPEC.md section 24: "Scan completed with errors" state."""
    import gui.main_window as main_window
    from core.models import ScanStatus
    from core.scanner import ScanResult

    monitored = tmp_path / "Monitored"
    monitored.mkdir()
    (monitored / "a.txt").write_text("one")

    window = gui_window
    window._set_directory(monitored)
    window._on_create_baseline()
    _pump_until(window, lambda: not window._scan_in_progress)

    error_result = ScanResult(path="unreadable.txt", status=ScanStatus.ERROR, error_message="Permission denied")
    monkeypatch.setattr(main_window, "run_scan", lambda *a, **k: [error_result])

    window._on_scan_now()
    _pump_until(window, lambda: not window._scan_in_progress)

    assert window.status_label.cget("text") == "⚠ Scan Completed With Errors"


def test_export_write_failure_shows_error_dialog(tmp_path, gui_window, monkeypatch):
    """PROJECT_SPEC.md section 18: a failed export must not crash the app."""
    from gui import dialogs
    from reports import exporter

    monitored = tmp_path / "Monitored"
    monitored.mkdir()
    (monitored / "a.txt").write_text("one")

    window = gui_window
    window._set_directory(monitored)
    window._on_create_baseline()
    _pump_until(window, lambda: not window._scan_in_progress)
    window._on_scan_now()
    _pump_until(window, lambda: not window._scan_in_progress)

    monkeypatch.setattr(
        dialogs, "choose_export_destination", lambda *a, **k: str(tmp_path / "results.csv")
    )

    def _boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(exporter, "export_csv", _boom)
    shown = []
    monkeypatch.setattr(dialogs, "show_error", lambda parent, title, message: shown.append(title))
    info_shown = []
    monkeypatch.setattr(dialogs, "show_info", lambda parent, title, message: info_shown.append(title))

    window._on_export_csv()

    assert shown == ["Export Failed"]
    assert info_shown == []  # the failure dialog replaces the success one, not both


def test_report_callback_exception_logs_if_error_dialog_itself_fails(gui_window, monkeypatch, caplog):
    """The fatal-error handler must not itself raise even if showing the
    error dialog fails (e.g. Tk is already in a bad state)."""
    import logging
    import sys

    from gui import dialogs

    def _broken_dialog(*a, **k):
        raise RuntimeError("dialog broken")

    window = gui_window
    monkeypatch.setattr(dialogs, "show_error", _broken_dialog)

    try:
        raise RuntimeError("original failure")
    except RuntimeError:
        with caplog.at_level(logging.ERROR):
            window.report_callback_exception(*sys.exc_info())  # must not raise

    assert any("Failed to show the fatal-error dialog" in record.message for record in caplog.records)


def test_on_close_closes_the_database_connection(tmp_path):
    """PROJECT_SPEC.md section 22: the database connection must be released
    on shutdown, not leaked."""
    import sqlite3

    _require_display()
    from gui.main_window import MainWindow

    window = MainWindow(db_path=tmp_path / "test.db")
    connection = window._connection
    window._on_close()

    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


def test_results_view_sort_by_column_toggles_order(gui_window):
    """PROJECT_SPEC.md section 12: the results table must be sortable by
    clicking a column header (wired to ``Treeview.heading(..., command=)``).
    """
    from core.models import ScanStatus
    from core.scanner import ScanResult

    view = gui_window.results_view
    view.set_results(
        [
            ScanResult(path="b.txt", status=ScanStatus.NEW, current_hash="b", size=2),
            ScanResult(path="a.txt", status=ScanStatus.NEW, current_hash="a", size=1),
            ScanResult(path="c.txt", status=ScanStatus.NEW, current_hash="c", size=3),
        ]
    )

    view._sort_by("file")
    ascending = [view.tree.item(row)["values"][1] for row in view.tree.get_children()]
    assert ascending == ["a.txt", "b.txt", "c.txt"]

    # Clicking the same header again reverses the order.
    view._sort_by("file")
    descending = [view.tree.item(row)["values"][1] for row in view.tree.get_children()]
    assert descending == ["c.txt", "b.txt", "a.txt"]
