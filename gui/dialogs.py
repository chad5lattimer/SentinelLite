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
    - The export-destination picker and scan-history browser (section 31,
      Run 6).
"""

from __future__ import annotations

from pathlib import Path
from tkinter import Button, Frame, Toplevel, filedialog, messagebox, ttk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from storage.repository import ScanMetadata


def choose_directory(parent, initial_dir: str | None = None) -> str | None:
    """Show a folder picker. Returns the chosen path, or ``None`` if cancelled."""
    chosen = filedialog.askdirectory(parent=parent, mustexist=True, initialdir=initial_dir or None)
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


def choose_export_destination(
    parent, file_type: str, initial_dir: Path, initial_file: str
) -> str | None:
    """Show a save-file dialog for exporting scan results (section 15).

    Args:
        file_type: ``"csv"`` or ``"json"`` -- selects the file-type filter
            and default extension.
        initial_dir: Directory the dialog opens in (the application's
            exports directory, section 22, by default).
        initial_file: Suggested file name.

    Returns:
        The chosen path, or ``None`` if the user cancelled.
    """
    filetypes = (
        [("CSV files", "*.csv"), ("All files", "*.*")]
        if file_type == "csv"
        else [("JSON files", "*.json"), ("All files", "*.*")]
    )
    chosen = filedialog.asksaveasfilename(
        parent=parent,
        title="Export Scan Results",
        defaultextension=f".{file_type}",
        filetypes=filetypes,
        initialdir=str(initial_dir),
        initialfile=initial_file,
    )
    return chosen or None


def show_scan_history(parent, scans: "list[ScanMetadata]") -> "ScanMetadata | None":
    """Show a modal list of past scans; returns the one the user picks.

    Per PROJECT_SPEC.md section 31 ("Scan history UI"). ``scans`` is
    expected most-recent-first (``storage.repository.list_scans``'s
    ordering). Returns ``None`` if the user closes the dialog without
    selecting a scan.
    """
    dialog = Toplevel(parent)
    dialog.title("Scan History")
    dialog.geometry("620x320")
    dialog.transient(parent)
    dialog.grab_set()

    columns = ("started", "completed", "modified", "new", "deleted", "unchanged", "errors")
    headings = {
        "started": "Started",
        "completed": "Completed",
        "modified": "Modified",
        "new": "New",
        "deleted": "Deleted",
        "unchanged": "Unchanged",
        "errors": "Errors",
    }
    tree = ttk.Treeview(dialog, columns=columns, show="headings")
    for column in columns:
        tree.heading(column, text=headings[column])
        tree.column(column, width=130 if column in ("started", "completed") else 70, anchor="w")
    tree.pack(fill="both", expand=True, padx=12, pady=(12, 8))

    for scan in scans:
        tree.insert(
            "",
            "end",
            iid=str(scan.scan_id),
            values=(
                scan.started_at,
                scan.completed_at or "",
                scan.modified_count,
                scan.new_count,
                scan.deleted_count,
                scan.unchanged_count,
                scan.error_count,
            ),
        )
    if scans:
        first_id = str(scans[0].scan_id)
        tree.selection_set(first_id)
        tree.focus(first_id)

    selection: list[int] = []

    def on_view() -> None:
        chosen = tree.selection()
        if chosen:
            selection.append(int(chosen[0]))
        dialog.destroy()

    def on_cancel() -> None:
        dialog.destroy()

    button_frame = Frame(dialog)
    button_frame.pack(fill="x", padx=12, pady=(0, 12))
    Button(button_frame, text="View Selected", command=on_view).pack(side="right", padx=(8, 0))
    Button(button_frame, text="Close", command=on_cancel).pack(side="right")

    tree.bind("<Double-1>", lambda _event: on_view())
    dialog.protocol("WM_DELETE_WINDOW", on_cancel)

    parent.wait_window(dialog)

    if not selection:
        return None
    chosen_id = selection[0]
    for scan in scans:
        if scan.scan_id == chosen_id:
            return scan
    return None
