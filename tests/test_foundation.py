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


def test_main_window_builds_and_closes():
    tk = pytest.importorskip("tkinter")
    try:
        probe = tk.Tk()
        probe.destroy()
    except tk.TclError:
        pytest.skip("No display available for GUI test.")

    from gui.main_window import MainWindow

    window = MainWindow()
    try:
        window.update_idletasks()
        assert window.title() == "SentinelLite - File Integrity Monitor"
        assert window.status_label.cget("text") == "Select a folder to begin."
        assert str(window.change_folder_button.cget("state")) == "disabled"
    finally:
        window.destroy()
