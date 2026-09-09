"""User-facing dialogs for SentinelLite.

Thin wrappers around Tk's standard dialogs, kept separate from
``main_window.py`` so the window module stays focused on layout and
state. Per PROJECT_SPEC.md section 5, this module contains presentation
only -- no hashing, filesystem, or comparison logic.

Covers:
    - The folder picker (section 11.2, "Change Folder").
    - The accidental-replacement confirmation before overwriting an
      existing baseline (section 9).
    - User-friendly error/info dialogs (section 18) -- callers are
      expected to supply plain-language text; raw tracebacks belong in the
      log, not here.
"""

from __future__ import annotations

from tkinter import filedialog, messagebox


def choose_directory(parent, initial_dir: str | None = None) -> str | None:
    """Show a folder picker. Returns the chosen path, or ``None`` if cancelled."""
    chosen = filedialog.askdirectory(parent=parent, mustexist=True, initialdir=initial_dir or None)
    return chosen or None


def choose_save_file(
    parent,
    *,
    default_name: str,
    extension: str,
    file_description: str,
) -> str | None:
    """Show a "Save As" dialog for a report export (PROJECT_SPEC.md section 15).

    Returns the chosen path, or ``None`` if cancelled.
    """
    chosen = filedialog.asksaveasfilename(
        parent=parent,
        title="Export Scan Results",
        initialfile=default_name,
        defaultextension=extension,
        filetypes=[(file_description, f"*{extension}"), ("All Files", "*.*")],
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
