"""Modal dialogs for SentinelLite.

Per PROJECT_SPEC.md section 9 (accidental baseline replacement must be
prevented) and section 18 (errors must be user-friendly, never raw
tracebacks): this module owns the small set of confirmation/info/error
popups the main window needs. It contains no hashing, filesystem, or
baseline logic of its own -- callers pass in already-computed values to
display.
"""

from __future__ import annotations

from tkinter import messagebox


def confirm_replace_baseline(parent, root_directory: str, existing_file_count: int) -> bool:
    """Ask the user to confirm replacing the active baseline.

    Per PROJECT_SPEC.md section 9, creating a new baseline replaces the
    monitoring reference, so the UI must not do this silently. Returns
    ``True`` only if the user explicitly confirms.
    """
    return messagebox.askyesno(
        parent=parent,
        title="Replace Baseline?",
        message=(
            "Creating a new baseline replaces the current monitoring "
            "reference.\n\n"
            f"The existing baseline for:\n{root_directory}\n\n"
            f"({existing_file_count:,} files) will stop being used for "
            "future scans, though it remains in scan history.\n\n"
            "Continue and create a new baseline?"
        ),
    )


def show_baseline_created(parent, root_directory: str, file_count: int, created_display: str) -> None:
    """Show the "Baseline Created" confirmation described in section 9."""
    messagebox.showinfo(
        parent=parent,
        title="Baseline Created",
        message=(
            f"Directory:\n{root_directory}\n\n"
            f"Files:\n{file_count:,}\n\n"
            f"Created:\n{created_display}\n\n"
            "Status:\n✓ Baseline Ready"
        ),
    )


def show_error(parent, title: str, detail: str) -> None:
    """Show a user-friendly error dialog (PROJECT_SPEC.md section 18).

    ``detail`` should already be a plain-language message -- callers are
    responsible for not passing raw tracebacks. Technical detail belongs in
    the application log, not this dialog.
    """
    messagebox.showerror(parent=parent, title=title, message=detail)


def show_warning(parent, title: str, detail: str) -> None:
    """Show a non-fatal, user-friendly warning (e.g. a scan completed but
    some files could not be read)."""
    messagebox.showwarning(parent=parent, title=title, message=detail)
