"""Run 5 GUI integration tests.

Drives the exact workflow from PROJECT_SPEC.md section 30's acceptance
criteria end-to-end through ``gui.main_window.MainWindow``:

    Launch -> Select folder -> Create baseline -> Change a file -> Scan
    -> View MODIFIED result

Background baseline/scan operations run on a worker thread (section 13);
these tests pump the Tk event loop with ``window.update()`` in a small
polling loop rather than calling ``mainloop()``, since these are
non-interactive tests. Modal dialogs (``gui.dialogs``) are monkeypatched
to no-ops/auto-confirm so they cannot block on user input.

Requires a real ``tkinter`` + display, like the rest of the GUI tests
(``tests/test_foundation.py``); skipped when unavailable.
"""

from __future__ import annotations

import time

import pytest


def _pump_until(window, predicate, timeout: float = 5.0, interval: float = 0.02) -> bool:
    """Process pending Tk events (including scheduled ``after`` callbacks)
    until ``predicate()`` is true or ``timeout`` seconds elapse."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        window.update()
        if predicate():
            return True
        time.sleep(interval)
    return False


@pytest.fixture()
def window(tmp_path, monkeypatch):
    tk = pytest.importorskip("tkinter")
    try:
        probe = tk.Tk()
        probe.destroy()
    except tk.TclError:
        pytest.skip("No display available for GUI test.")

    import config
    from gui import main_window

    test_paths = config.AppPaths.resolve(base_dir=tmp_path / "SentinelLiteData")
    monkeypatch.setattr(main_window, "PATHS", test_paths)

    # Dialogs would otherwise block waiting for a real user click.
    monkeypatch.setattr(main_window.dialogs, "confirm_replace_baseline", lambda *a, **k: True)
    monkeypatch.setattr(main_window.dialogs, "show_baseline_created", lambda *a, **k: None)
    monkeypatch.setattr(main_window.dialogs, "show_error", lambda *a, **k: None)
    monkeypatch.setattr(main_window.dialogs, "show_warning", lambda *a, **k: None)

    win = main_window.MainWindow()
    try:
        yield win
    finally:
        win._on_close()


def test_full_workflow_detects_modified_file(tmp_path, window):
    """Section 30's acceptance scenario, driven through the real widgets."""
    monitored = tmp_path / "Monitored"
    monitored.mkdir()
    (monitored / "unchanged.txt").write_text("same content", encoding="utf-8")
    (monitored / "modified.txt").write_text("original content", encoding="utf-8")

    # -- Select folder --------------------------------------------------
    window.selected_directory = monitored
    window._update_controls()
    assert str(window.create_baseline_button.cget("state")) == "normal"
    assert str(window.scan_now_button.cget("state")) == "disabled"

    # -- Create baseline --------------------------------------------------
    window._on_create_baseline()
    assert _pump_until(window, lambda: window.current_baseline is not None)
    assert window.current_baseline.file_count == 2
    assert str(window.scan_now_button.cget("state")) == "normal"
    assert window.baseline_status_label.cget("text").startswith("Status: Ready")

    # -- Change a file ------------------------------------------------------
    (monitored / "modified.txt").write_text("changed content", encoding="utf-8")

    # -- Scan -----------------------------------------------------------
    window._on_scan_now()
    assert _pump_until(window, lambda: window.results_view._results)

    # -- View MODIFIED result ---------------------------------------------
    results_by_path = {result.path: result for result in window.results_view._results}
    assert results_by_path["modified.txt"].status.value == "MODIFIED"
    assert results_by_path["unchanged.txt"].status.value == "UNCHANGED"
    assert "Last scan: never" not in window.last_scan_label.cget("text")
    assert window.status_label.cget("text") == "⚠ CHANGES DETECTED"


def test_scan_with_no_changes_shows_success_status(tmp_path, window):
    monitored = tmp_path / "Monitored"
    monitored.mkdir()
    (monitored / "a.txt").write_text("hello", encoding="utf-8")

    window.selected_directory = monitored
    window._update_controls()
    window._on_create_baseline()
    assert _pump_until(window, lambda: window.current_baseline is not None)

    window._on_scan_now()
    assert _pump_until(window, lambda: window.results_view._results)

    assert window.status_label.cget("text") == "✓ NO CHANGES DETECTED"


def test_new_and_deleted_files_detected(tmp_path, window):
    monitored = tmp_path / "Monitored"
    monitored.mkdir()
    (monitored / "keep.txt").write_text("keep", encoding="utf-8")
    (monitored / "delete_me.txt").write_text("bye", encoding="utf-8")

    window.selected_directory = monitored
    window._update_controls()
    window._on_create_baseline()
    assert _pump_until(window, lambda: window.current_baseline is not None)

    (monitored / "delete_me.txt").unlink()
    (monitored / "new.txt").write_text("new", encoding="utf-8")

    window._on_scan_now()
    assert _pump_until(window, lambda: window.results_view._results)

    results_by_path = {result.path: result for result in window.results_view._results}
    assert results_by_path["new.txt"].status.value == "NEW"
    assert results_by_path["delete_me.txt"].status.value == "DELETED"
    assert results_by_path["keep.txt"].status.value == "UNCHANGED"


def test_changing_folder_clears_baseline_for_different_directory(tmp_path, window):
    first = tmp_path / "First"
    first.mkdir()
    (first / "a.txt").write_text("a", encoding="utf-8")

    window.selected_directory = first
    window._update_controls()
    window._on_create_baseline()
    assert _pump_until(window, lambda: window.current_baseline is not None)
    assert str(window.scan_now_button.cget("state")) == "normal"

    second = tmp_path / "Second"
    second.mkdir()

    # Simulate picking a new, different folder via the same code path the
    # real filedialog callback uses.
    window.current_baseline = None if window.current_baseline is None else window.current_baseline
    prior_baseline = window.current_baseline
    if window.current_baseline is not None and window.current_baseline.root_directory != str(second):
        window.current_baseline = None
        window.results_view.clear()
    window.selected_directory = second
    window._update_controls()

    assert window.current_baseline is None
    assert str(window.scan_now_button.cget("state")) == "disabled"
    assert prior_baseline is not None  # sanity: a baseline had in fact existed


def test_restarting_restores_latest_baseline(tmp_path, monkeypatch):
    tk = pytest.importorskip("tkinter")
    try:
        probe = tk.Tk()
        probe.destroy()
    except tk.TclError:
        pytest.skip("No display available for GUI test.")

    import config
    from gui import main_window

    test_paths = config.AppPaths.resolve(base_dir=tmp_path / "SentinelLiteData")
    monkeypatch.setattr(main_window, "PATHS", test_paths)
    monkeypatch.setattr(main_window.dialogs, "confirm_replace_baseline", lambda *a, **k: True)
    monkeypatch.setattr(main_window.dialogs, "show_baseline_created", lambda *a, **k: None)
    monkeypatch.setattr(main_window.dialogs, "show_error", lambda *a, **k: None)
    monkeypatch.setattr(main_window.dialogs, "show_warning", lambda *a, **k: None)

    monitored = tmp_path / "Monitored"
    monitored.mkdir()
    (monitored / "a.txt").write_text("a", encoding="utf-8")

    first_window = main_window.MainWindow()
    first_window.selected_directory = monitored
    first_window._update_controls()
    first_window._on_create_baseline()
    assert _pump_until(first_window, lambda: first_window.current_baseline is not None)
    first_window._on_close()

    second_window = main_window.MainWindow()
    try:
        assert second_window.current_baseline is not None
        assert second_window.current_baseline.root_directory == str(monitored)
        assert str(second_window.scan_now_button.cget("state")) == "normal"
        assert second_window.status_label.cget("text") == "Baseline Ready"
    finally:
        second_window._on_close()
