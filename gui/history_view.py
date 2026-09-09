"""Scan history dialog for SentinelLite (PROJECT_SPEC.md section 30 - Run 6).

Lists previously completed scans for the active baseline (persisted by
``core.scanner.save_scan`` / ``storage.repository``, section 14) and lets
the user reload a past scan's results into the main results view, or
export it directly. Pure presentation -- it reads through
``storage.repository`` / ``core.scanner`` but performs no hashing,
filesystem, or comparison logic itself (section 5).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from tkinter import ttk
from typing import Callable

import customtkinter as ctk

from core.scanner import ScanResult, get_scan_results, list_scans
from storage.repository import ScanMetadata

_COLUMNS: tuple[str, ...] = ("date", "modified", "new", "deleted", "unchanged", "errors")
_HEADINGS: dict[str, str] = {
    "date": "Completed",
    "modified": "Modified",
    "new": "New",
    "deleted": "Deleted",
    "unchanged": "Unchanged",
    "errors": "Errors",
}


def _format_display_time(iso_timestamp: str | None) -> str:
    if not iso_timestamp:
        return "In progress"
    try:
        parsed = datetime.fromisoformat(iso_timestamp)
    except ValueError:
        return iso_timestamp
    return parsed.strftime("%b %d, %Y %I:%M %p")


class ScanHistoryDialog(ctk.CTkToplevel):
    """Modal dialog listing scan history for one baseline.

    Args:
        master: The parent window.
        connection: Database connection to read scan history from. Only
            used from the GUI thread (this dialog performs no background
            work of its own -- history reads are fast, indexed lookups).
        baseline_id: The baseline whose scan history is shown.
        on_view_results: Called with ``(list[ScanResult], display_timestamp)``
            when the user chooses to view a past scan's results in the main
            window.
        on_export: Called with ``(file_format, scan_id, list[ScanResult],
            display_timestamp)`` when the user chooses to export a past
            scan. ``file_format`` is ``"csv"`` or ``"json"``.
    """

    def __init__(
        self,
        master,
        connection: sqlite3.Connection,
        baseline_id: int,
        *,
        on_view_results: Callable[[list[ScanResult], str], None],
        on_export: Callable[[str, int, list[ScanResult], str], None],
    ) -> None:
        super().__init__(master)
        self.title("Scan History")
        self.geometry("560x360")
        self.transient(master)

        self._connection = connection
        self._on_view_results = on_view_results
        self._on_export = on_export
        self._scans: list[ScanMetadata] = list_scans(connection, baseline_id=baseline_id)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_table()
        self._build_actions()
        self._render_rows()

        self.grab_set()

    def _build_table(self) -> None:
        table_frame = ctk.CTkFrame(self, fg_color="transparent")
        table_frame.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 6))
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(table_frame, columns=_COLUMNS, show="headings")
        for column in _COLUMNS:
            self.tree.heading(column, text=_HEADINGS[column])
            width = 160 if column == "date" else 80
            self.tree.column(column, width=width, anchor="w")

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        if not self._scans:
            self.tree.insert("", "end", values=("No scans recorded yet.", "", "", "", "", ""))

    def _build_actions(self) -> None:
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
        actions.grid_columnconfigure(3, weight=1)

        ctk.CTkButton(actions, text="View Results", command=self._on_view_clicked).grid(
            row=0, column=0, padx=(0, 8)
        )
        ctk.CTkButton(actions, text="Export CSV", command=lambda: self._on_export_clicked("csv")).grid(
            row=0, column=1, padx=(0, 8)
        )
        ctk.CTkButton(actions, text="Export JSON", command=lambda: self._on_export_clicked("json")).grid(
            row=0, column=2, padx=(0, 8)
        )
        ctk.CTkButton(actions, text="Close", command=self.destroy).grid(row=0, column=4, sticky="e")

    def _render_rows(self) -> None:
        for scan in self._scans:
            self.tree.insert(
                "",
                "end",
                iid=str(scan.scan_id),
                values=(
                    _format_display_time(scan.completed_at),
                    scan.modified_count,
                    scan.new_count,
                    scan.deleted_count,
                    scan.unchanged_count,
                    scan.error_count,
                ),
            )

    def _selected_scan(self) -> ScanMetadata | None:
        selection = self.tree.selection()
        if not selection:
            return None
        scan_id = int(selection[0])
        return next((scan for scan in self._scans if scan.scan_id == scan_id), None)

    def _on_view_clicked(self) -> None:
        scan = self._selected_scan()
        if scan is None:
            return
        results = get_scan_results(self._connection, scan.scan_id)
        self._on_view_results(results, _format_display_time(scan.completed_at))
        self.destroy()

    def _on_export_clicked(self, file_format: str) -> None:
        scan = self._selected_scan()
        if scan is None:
            return
        results = get_scan_results(self._connection, scan.scan_id)
        self._on_export(file_format, scan.scan_id, results, _format_display_time(scan.completed_at))
