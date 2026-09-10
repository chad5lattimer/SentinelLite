"""Scan history dialog for SentinelLite (PROJECT_SPEC.md section 31 - Run 6).

Lists previously completed scans for the active baseline and lets the user
reload one into the main results view/table. Presentation only -- it is
handed already-fetched ``core.scanner.ScanMetadata`` rows and performs no
hashing, filesystem, or comparison logic itself (PROJECT_SPEC.md section 5).
"""

from __future__ import annotations

from tkinter import ttk
from typing import Callable

import customtkinter as ctk

from core.scanner import ScanMetadata
from gui.formatting import format_display_time

_COLUMNS: tuple[str, ...] = ("date", "modified", "new", "deleted", "unchanged", "errors")
_HEADINGS: dict[str, str] = {
    "date": "Date",
    "modified": "Modified",
    "new": "New",
    "deleted": "Deleted",
    "unchanged": "Unchanged",
    "errors": "Errors",
}


class ScanHistoryDialog(ctk.CTkToplevel):
    """A modal listing past scans, most recent first.

    Double-clicking (or selecting and pressing "View Selected") a row calls
    ``on_select`` with that scan's ``ScanMetadata`` and closes the dialog.
    """

    def __init__(
        self,
        parent,
        scans: list[ScanMetadata],
        on_select: Callable[[ScanMetadata], None],
    ) -> None:
        super().__init__(parent)
        self._on_select = on_select
        self._scans_by_row_id: dict[str, ScanMetadata] = {}

        self.title("Scan History")
        self.geometry("620x360")
        self.minsize(480, 260)
        self.transient(parent)

        ctk.CTkLabel(
            self, text="Scan History", font=ctk.CTkFont(size=16, weight="bold")
        ).pack(padx=16, pady=(16, 8), anchor="w")

        self.tree = ttk.Treeview(self, columns=_COLUMNS, show="headings")
        for column in _COLUMNS:
            self.tree.heading(column, text=_HEADINGS[column])
            self.tree.column(column, width=170 if column == "date" else 80, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        self.tree.bind("<Double-1>", lambda _event: self._select_current())

        for scan in scans:
            display_time = (
                format_display_time(scan.completed_at) if scan.completed_at else "In progress"
            )
            row_id = self.tree.insert(
                "",
                "end",
                values=(
                    display_time,
                    scan.modified_count,
                    scan.new_count,
                    scan.deleted_count,
                    scan.unchanged_count,
                    scan.error_count,
                ),
            )
            self._scans_by_row_id[row_id] = scan

        button_row = ctk.CTkFrame(self, fg_color="transparent")
        button_row.pack(fill="x", padx=16, pady=(0, 16))

        ctk.CTkButton(button_row, text="View Selected", command=self._select_current).pack(
            side="right"
        )
        ctk.CTkButton(
            button_row,
            text="Close",
            command=self.destroy,
            fg_color="transparent",
            border_width=1,
        ).pack(side="right", padx=(0, 8))

        # Select the most recent scan (first row) by default for convenience.
        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])

    def _select_current(self) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        scan = self._scans_by_row_id[selection[0]]
        self.destroy()
        self._on_select(scan)
