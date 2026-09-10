"""User-facing dialogs for SentinelLite.

Thin wrappers around Tk's standard dialogs, kept separate from
``main_window.py`` so the window module stays focused on layout and
state. Per PROJECT_SPEC.md section 5, this module contains presentation
only -- no hashing, filesystem, or comparison logic.

Covers:
    - The folder picker (section 11.2, "Change Folder").
    - The accidental-replacement confirmation before overwriting an
      existing baseline (section 9).
    - The save-file picker used when exporting scan results (section 15).
    - User-friendly error/info dialogs (section 18) -- callers are
      expected to supply plain-language text; raw tracebacks belong in the
      log, not here.
"""

from __future__ import annotations

from tkinter import filedialog, messagebox

#: File-dialog filters for each supported export format (section 15).
_EXPORT_FILE_TYPES: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "csv": (".csv", [("CSV files", "*.csv"), ("All files", "*.*")]),
    "json": (".json", [("JSON files", "*.json"), ("All files", "*.*")]),
}


def choose_directory(parent, initial_dir: str | None = None) -> str | None:
    """Show a folder picker. Returns the chosen path, or ``None`` if cancelled."""
    chosen = filedialog.askdirectory(parent=parent, mustexist=True, initialdir=initial_dir or None)
    return chosen or None


def choose_export_destination(
    parent, *, file_type: str, initial_dir: str | None = None, initial_file: str | None = None
) -> str | None:
    """Show a save-file picker for exporting scan results (section 15).

    Args:
        file_type: ``"csv"`` or ``"json"``.
        initial_dir: Folder the dialog should open in (e.g. the app's
            exports directory).
        initial_file: Suggested filename.

    Returns:
        The chosen destination path, or ``None`` if the user cancelled.
    """
    default_extension, filetypes = _EXPORT_FILE_TYPES[file_type]
    chosen = filedialog.asksaveasfilename(
        parent=parent,
        title="Export Scan Results",
        initialdir=initial_dir or None,
        initialfile=initial_file or None,
        defaultextension=default_extension,
        filetypes=filetypes,
    )
    return chosen or None


def confirm_replace_baseline(parent) -> bool:
    """Warn that creating a new baseline replaces the monitoring reference.

    Per PROJECT_SPEC.md section 9: "The UI should prevent accidental
    replacement." Returns ``True`` if the user confirms.
    """
    return messagebox.askyesno(
        parent=parent,
        title="Replace Baseline?",
        message=(
            "Creating a new baseline replaces the current monitoring "
            "reference for this folder.\n\n"
            "Future scans will compare against the new baseline. "
            "Previous scan history is kept.\n\n"
            "Continue?"
        ),
    )


def show_error(parent, title: str, message: str) -> None:
    """Display a user-friendly error dialog (PROJECT_SPEC.md section 18)."""
    messagebox.showerror(parent=parent, title=title, message=message)


def show_info(parent, title: str, message: str) -> None:
    """Display an informational dialog (e.g. "Baseline Created")."""
    messagebox.showinfo(parent=parent, title=title, message=message)
