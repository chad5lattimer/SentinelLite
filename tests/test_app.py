"""Tests for app.py, the application entry point (PROJECT_SPEC.md section 26).

``app.main()`` was the one remaining module with no dedicated tests --
every other module under ``core/``, ``storage/``, ``gui/``, ``reports/``,
and ``config.py`` sits at 100% coverage, but ``app.py`` sat at 0% since no
test ever imported or executed it. Its two seams (``MainWindow`` and
``configure_logging``) are monkeypatched here, the same pattern used
throughout ``tests/test_gui_integration.py`` and ``tests/test_dialogs.py``,
so these tests run headless and never open a real window or touch the
real per-user application data directory.

``app.py`` imports ``gui.main_window`` unconditionally at module level,
which in turn imports ``customtkinter`` (and therefore ``tkinter``) --
so, consistent with ``tests/test_dialogs.py``, this whole module is
skipped via ``pytest.importorskip`` in environments where the ``tkinter``
package itself isn't installed. That is a stricter condition than "no
display" (``tests/test_gui_integration.py``'s ``_require_display()``):
none of these tests open a real window, so no display is needed, but the
package must be importable.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest

pytest.importorskip("tkinter")

import app


class _FakeWindow:
    """Stand-in for gui.main_window.MainWindow that never opens a display."""

    def __init__(self):
        self.mainloop_called = False

    def mainloop(self):
        self.mainloop_called = True


def test_main_configures_logging_builds_window_and_runs_mainloop(monkeypatch, tmp_path):
    fake_log_file = tmp_path / "sentinellite.log"
    configure_calls = []
    windows_created = []

    def fake_configure_logging():
        configure_calls.append(True)
        return fake_log_file

    def fake_main_window_factory():
        window = _FakeWindow()
        windows_created.append(window)
        return window

    monkeypatch.setattr(app, "configure_logging", fake_configure_logging)
    monkeypatch.setattr(app, "MainWindow", fake_main_window_factory)

    exit_code = app.main()

    assert exit_code == 0
    assert configure_calls == [True]
    assert len(windows_created) == 1
    assert windows_created[0].mainloop_called


def test_main_logs_and_reraises_when_window_creation_fails(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(app, "configure_logging", lambda: tmp_path / "sentinellite.log")

    def failing_main_window():
        raise RuntimeError("no display available")

    monkeypatch.setattr(app, "MainWindow", failing_main_window)

    with caplog.at_level("ERROR"):
        with pytest.raises(RuntimeError, match="no display available"):
            app.main()

    assert "Failed to create the main window." in caplog.text


def test_main_logs_shutdown_even_if_mainloop_raises(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(app, "configure_logging", lambda: tmp_path / "sentinellite.log")

    class _RaisingWindow:
        def mainloop(self):
            raise RuntimeError("event loop blew up")

    monkeypatch.setattr(app, "MainWindow", _RaisingWindow)

    with caplog.at_level("INFO"):
        with pytest.raises(RuntimeError, match="event loop blew up"):
            app.main()

    assert "shutting down" in caplog.text.lower()


def test_entrypoint_guard_calls_main_and_exits_with_its_return_code(monkeypatch, tmp_path):
    """Exercises the ``if __name__ == "__main__":`` line itself -- the only
    line the tests above don't reach, since they call ``app.main()``
    directly -- by running the module as a script via ``runpy``, with the
    same two seams patched beforehand on the real ``config``/
    ``gui.main_window`` modules (app.py imports both names directly, so
    patching the source modules before re-executing the ``from ... import``
    statements is what takes effect)."""
    import config as config_module
    from gui import main_window as main_window_module

    windows_created = []

    def fake_main_window_factory():
        window = _FakeWindow()
        windows_created.append(window)
        return window

    monkeypatch.setattr(config_module, "configure_logging", lambda: tmp_path / "sentinellite.log")
    monkeypatch.setattr(main_window_module, "MainWindow", fake_main_window_factory)

    exit_codes = []
    monkeypatch.setattr(sys, "exit", lambda code=0: exit_codes.append(code))

    runpy.run_path(str(Path(__file__).resolve().parent.parent / "app.py"), run_name="__main__")

    assert exit_codes == [0]
    assert len(windows_created) == 1
    assert windows_created[0].mainloop_called
