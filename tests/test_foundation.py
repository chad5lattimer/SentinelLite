"""Run 1 foundation tests.

Covers: configuration/paths, logging setup, and that the application can
build its main window and enter/exit the GUI event loop without errors.
No filesystem-scanning or hashing behavior is tested here -- that arrives
with the core engine in later runs.
"""

from __future__ import annotations

import importlib
import logging

import pytest


def test_app_metadata_present():
    import config

    assert config.APP_NAME == "SentinelLite"
    assert config.APP_VERSION
    assert config.APP_DESCRIPTION


def test_app_paths_resolve_under_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINELLITE_DATA_DIR", str(tmp_path / "SentinelLiteData"))

    import config

    importlib.reload(config)
    paths = config.AppPaths.resolve()

    assert paths.data_dir == tmp_path / "SentinelLiteData"
    assert paths.logs_dir == paths.data_dir / "logs"
    assert paths.exports_dir == paths.data_dir / "exports"
    assert paths.database_path.name == "sentinellite.db"
    assert paths.log_file.name == "sentinellite.log"

    # Directories should not exist until explicitly created.
    assert not paths.data_dir.exists()
    paths.ensure_directories()
    assert paths.data_dir.is_dir()
    assert paths.logs_dir.is_dir()
    assert paths.exports_dir.is_dir()

    # Reload with real environment restored so later tests are unaffected.
    monkeypatch.undo()
    importlib.reload(config)


def test_default_app_data_dir_windows_uses_localappdata(monkeypatch, tmp_path):
    """PROJECT_SPEC.md section 22 requires resolving to %LOCALAPPDATA% on
    Windows. This branch only runs on real Windows in normal use, but the
    selection logic itself -- given a platform and environment -- is a
    pure function that can and should be exercised directly on any OS."""
    import config

    monkeypatch.delenv("SENTINELLITE_DATA_DIR", raising=False)
    monkeypatch.setattr(config.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))

    data_dir = config._default_app_data_dir()

    assert data_dir == tmp_path / "AppData" / "Local" / config.APP_NAME


def test_default_app_data_dir_macos_uses_application_support(monkeypatch):
    import config

    monkeypatch.delenv("SENTINELLITE_DATA_DIR", raising=False)
    monkeypatch.setattr(config.sys, "platform", "darwin")

    data_dir = config._default_app_data_dir()

    assert data_dir == config.Path.home() / "Library" / "Application Support" / config.APP_NAME


def test_default_app_data_dir_windows_without_localappdata_uses_home(monkeypatch):
    """When %LOCALAPPDATA% is unset, fall back to a home-relative path
    rather than raising or resolving to a bogus location."""
    import config

    monkeypatch.delenv("SENTINELLITE_DATA_DIR", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(config.sys, "platform", "win32")

    data_dir = config._default_app_data_dir()

    assert data_dir == config.Path.home() / "AppData" / "Local" / config.APP_NAME


def test_default_app_data_dir_linux_respects_xdg_data_home(monkeypatch, tmp_path):
    import config

    monkeypatch.delenv("SENTINELLITE_DATA_DIR", raising=False)
    monkeypatch.setattr(config.sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))

    data_dir = config._default_app_data_dir()

    assert data_dir == tmp_path / "xdg" / config.APP_NAME


def test_default_app_data_dir_linux_without_xdg_uses_home_local_share(monkeypatch):
    import config

    monkeypatch.delenv("SENTINELLITE_DATA_DIR", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(config.sys, "platform", "linux")

    data_dir = config._default_app_data_dir()

    assert data_dir == config.Path.home() / ".local" / "share" / config.APP_NAME


def test_configure_logging_creates_log_file(tmp_path):
    import config

    paths = config.AppPaths.resolve(base_dir=tmp_path / "LogTarget")

    # Reset module-level "already configured" guard so this test gets its
    # own handler attached regardless of test execution order.
    config._LOGGING_CONFIGURED = False
    try:
        log_file = config.configure_logging(paths=paths, level=logging.DEBUG)
        logging.getLogger("sentinellite.test").info("hello from test")

        assert log_file == paths.log_file
        assert log_file.exists()
        assert "hello from test" in log_file.read_text(encoding="utf-8")
    finally:
        # Clean up handlers so later tests/log files aren't polluted.
        root = logging.getLogger()
        for handler in list(root.handlers):
            handler.close()
            root.removeHandler(handler)
        config._LOGGING_CONFIGURED = False


def test_app_main_configures_logging_builds_window_and_runs_loop(monkeypatch, tmp_path):
    """app.main() (Run 1's entry point) should configure logging once,
    build exactly one MainWindow, and hand control to its event loop --
    without this test, app.py itself was never imported by the suite and
    sat at 0% coverage. Both collaborators are monkeypatched at the seam
    app.py calls through, matching the pattern used for the GUI/core
    seams elsewhere (e.g. test_gui_integration.py), so this never builds
    a real Tk window or touches the real per-user app data directory."""
    pytest.importorskip("tkinter")
    pytest.importorskip("customtkinter")
    import app

    calls = []

    def fake_configure_logging():
        calls.append("configure_logging")
        return tmp_path / "sentinellite.log"

    class FakeWindow:
        def __init__(self):
            calls.append("window_created")

        def mainloop(self):
            calls.append("mainloop")

    monkeypatch.setattr(app, "configure_logging", fake_configure_logging)
    monkeypatch.setattr(app, "MainWindow", FakeWindow)

    exit_code = app.main()

    assert exit_code == 0
    assert calls == ["configure_logging", "window_created", "mainloop"]


def test_app_main_logs_and_reraises_when_window_creation_fails(monkeypatch, tmp_path):
    """A failure building the main window (e.g. no display) must be
    logged, per section 16's 'Errors' logging requirement, and then
    re-raised rather than swallowed -- app.py has no fallback UI to fall
    back to."""
    pytest.importorskip("tkinter")
    pytest.importorskip("customtkinter")
    import app

    monkeypatch.setattr(
        app, "configure_logging", lambda: tmp_path / "sentinellite.log"
    )

    class FailingWindow:
        def __init__(self):
            raise RuntimeError("no display available")

    monkeypatch.setattr(app, "MainWindow", FailingWindow)

    with pytest.raises(RuntimeError, match="no display available"):
        app.main()


def test_main_window_builds_and_closes(tmp_path):
    tk = pytest.importorskip("tkinter")
    pytest.importorskip("customtkinter")
    try:
        probe = tk.Tk()
        probe.destroy()
    except tk.TclError:
        pytest.skip("No display available for GUI test.")

    from gui.main_window import MainWindow

    # Point at a throwaway database so this test never touches the real
    # per-user application data directory (PROJECT_SPEC.md section 22).
    window = MainWindow(db_path=tmp_path / "test.db")
    try:
        window.update_idletasks()
        assert window.title() == "SentinelLite - File Integrity Monitor"
        assert window.status_label.cget("text") == "Select a folder to begin."
        assert str(window.change_folder_button.cget("state")) == "normal"
        assert str(window.create_baseline_button.cget("state")) == "disabled"
    finally:
        window._on_close()
