"""Direct unit tests for gui.dialogs (PROJECT_SPEC.md section 5 -
Architecture, section 9 - Baseline Creation, section 15 - Report Export,
section 18 - Error Handling, section 19/35 - "testable independently").

``tests/test_gui_integration.py`` already exercises the GUI workflow, but
it deliberately monkeypatches every function in this module (via
``monkeypatch.setattr(dialogs, ...)``) so tests never block on a real
modal dialog -- which means the actual bodies of ``gui/dialogs.py`` are
never executed by any existing test. This file closes that gap directly:
it monkeypatches the underlying ``tkinter.filedialog`` / ``messagebox``
calls instead, so ``gui/dialogs.py``'s own logic (argument construction,
the "empty string means cancelled" -> ``None`` conversion) runs for real.
Because only the stdlib ``tkinter.filedialog``/``messagebox`` functions
are replaced, this needs no real Tk display or event loop.
"""

from __future__ import annotations

import pytest

tk = pytest.importorskip("tkinter")
filedialog = pytest.importorskip("tkinter.filedialog")
messagebox = pytest.importorskip("tkinter.messagebox")

from gui import dialogs

_PARENT = object()


# --- choose_directory ----------------------------------------------------


def test_choose_directory_returns_chosen_path(monkeypatch):
    captured = {}

    def fake_askdirectory(**kwargs):
        captured.update(kwargs)
        return "/monitored/folder"

    monkeypatch.setattr(filedialog, "askdirectory", fake_askdirectory)

    result = dialogs.choose_directory(_PARENT, initial_dir="/start/here")

    assert result == "/monitored/folder"
    assert captured == {"parent": _PARENT, "mustexist": True, "initialdir": "/start/here"}


def test_choose_directory_returns_none_when_cancelled(monkeypatch):
    monkeypatch.setattr(filedialog, "askdirectory", lambda **kwargs: "")

    assert dialogs.choose_directory(_PARENT) is None


def test_choose_directory_without_initial_dir_passes_none(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        filedialog, "askdirectory", lambda **kwargs: captured.update(kwargs) or ""
    )

    dialogs.choose_directory(_PARENT)

    assert captured["initialdir"] is None


# --- choose_export_destination --------------------------------------------


def test_choose_export_destination_csv_uses_csv_filters(monkeypatch):
    captured = {}

    def fake_asksaveasfilename(**kwargs):
        captured.update(kwargs)
        return "/exports/results.csv"

    monkeypatch.setattr(filedialog, "asksaveasfilename", fake_asksaveasfilename)

    result = dialogs.choose_export_destination(
        _PARENT, file_type="csv", initial_dir="/exports", initial_file="results.csv"
    )

    assert result == "/exports/results.csv"
    assert captured["defaultextension"] == ".csv"
    assert captured["filetypes"] == [("CSV files", "*.csv"), ("All files", "*.*")]
    assert captured["initialdir"] == "/exports"
    assert captured["initialfile"] == "results.csv"
    assert captured["parent"] is _PARENT


def test_choose_export_destination_json_uses_json_filters(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        filedialog, "asksaveasfilename", lambda **kwargs: captured.update(kwargs) or "out.json"
    )

    dialogs.choose_export_destination(_PARENT, file_type="json")

    assert captured["defaultextension"] == ".json"
    assert captured["filetypes"] == [("JSON files", "*.json"), ("All files", "*.*")]
    assert captured["initialdir"] is None
    assert captured["initialfile"] is None


def test_choose_export_destination_returns_none_when_cancelled(monkeypatch):
    monkeypatch.setattr(filedialog, "asksaveasfilename", lambda **kwargs: "")

    assert dialogs.choose_export_destination(_PARENT, file_type="csv") is None


def test_choose_export_destination_rejects_unknown_file_type():
    with pytest.raises(KeyError):
        dialogs.choose_export_destination(_PARENT, file_type="xml")


# --- confirm_replace_baseline ---------------------------------------------


def test_confirm_replace_baseline_returns_user_choice(monkeypatch):
    captured = {}

    def fake_askyesno(**kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(messagebox, "askyesno", fake_askyesno)

    assert dialogs.confirm_replace_baseline(_PARENT) is True
    assert captured["parent"] is _PARENT
    assert captured["title"] == "Replace Baseline?"
    assert "replaces" in captured["message"].lower()


def test_confirm_replace_baseline_false_when_declined(monkeypatch):
    monkeypatch.setattr(messagebox, "askyesno", lambda **kwargs: False)

    assert dialogs.confirm_replace_baseline(_PARENT) is False


# --- show_error / show_info -----------------------------------------------


def test_show_error_forwards_title_and_message(monkeypatch):
    captured = {}
    monkeypatch.setattr(messagebox, "showerror", lambda **kwargs: captured.update(kwargs))

    dialogs.show_error(_PARENT, "Unable to read file", "The scan will continue.")

    assert captured == {
        "parent": _PARENT,
        "title": "Unable to read file",
        "message": "The scan will continue.",
    }


def test_show_info_forwards_title_and_message(monkeypatch):
    captured = {}
    monkeypatch.setattr(messagebox, "showinfo", lambda **kwargs: captured.update(kwargs))

    dialogs.show_info(_PARENT, "Baseline Created", "1,284 files.")

    assert captured == {
        "parent": _PARENT,
        "title": "Baseline Created",
        "message": "1,284 files.",
    }
