"""Scan results view for SentinelLite (PROJECT_SPEC.md section 12).

Displays summary statistics and a sortable/filterable table of per-file
scan results. This is pure presentation -- it receives already-computed
``core.scanner.ScanResult`` objects and performs no hashing or comparison
logic itself (PROJECT_SPEC.md section 5).

The table uses ``tkinter.ttk.Treeview`` rather than a CustomTkinter widget:
CustomTkinter has no built-in table widget, and Treeview embeds cleanly
inside a CTk layout.
"""

from __future__ import annotations

from tkinter import ttk
from typing import Callable, Iterable

import customtkinter as ctk

from core.models import ScanStatus
from core.scanner import ScanResult, ScanSummary

#: Filter options, per PROJECT_SPEC.md section 12.
FILTER_OPTIONS: tuple[str, ...] = ("All", "Modified", "New", "Deleted", "Unchanged", "Errors")

_FILTER_TO_STATUS = {
    "Modified": ScanStatus.MODIFIED,
    "New": ScanStatus.NEW,
    "Deleted": ScanStatus.DELETED,
    "Unchanged": ScanStatus.UNCHANGED,
    "Errors": ScanStatus.ERROR,
}

_STATUS_TAG = {
    ScanStatus.MODIFIED: "modified",
    ScanStatus.NEW: "new",
    ScanStatus.DELETED: "deleted",
    ScanStatus.UNCHANGED: "unchanged",
    ScanStatus.ERROR: "error",
}

_COLUMNS: tuple[str, ...] = ("status", "file", "baseline_hash", "current_hash", "size", "timestamp")
_HEADINGS: dict[str, str] = {
    "status": "Status",
    "file": "File",
    "baseline_hash": "Baseline Hash",
    "current_hash": "Current Hash",
    "size": "Size",
    "timestamp": "Timestamp",
}


class ResultsView(ctk.CTkFrame):
    """Summary statistics plus a filterable, sortable results table."""

    def __init__(
        self,
        master,
        on_export_csv: Callable[[], None] | None = None,
        on_export_json: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, fg_color="transparent")

        self._results: list[ScanResult] = []
        self._timestamp = ""
        self._active_filter = "All"
        self._sort_reverse: dict[str, bool] = {}
        self._export_csv_callback = on_export_csv
        self._export_json_callback = on_export_json

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_summary()
        self._build_filter()
        self._build_table()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_summary(self) -> None:
        summary_frame = ctk.CTkFrame(self, fg_color="transparent")
        summary_frame.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 8))

        self._summary_labels: dict[str, ctk.CTkLabel] = {}
        for column, name in enumerate(("Modified", "New", "Deleted", "Unchanged", "Errors")):
            label = ctk.CTkLabel(summary_frame, text=f"{name}: 0", font=ctk.CTkFont(weight="bold"))
            label.grid(row=0, column=column, padx=10, sticky="w")
            self._summary_labels[name] = label

    def _build_filter(self) -> None:
        control_row = ctk.CTkFrame(self, fg_color="transparent")
        control_row.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 8))
        control_row.grid_columnconfigure(0, weight=1)

        self.filter_control = ctk.CTkSegmentedButton(
            control_row, values=list(FILTER_OPTIONS), command=self._on_filter_changed
        )
        self.filter_control.set("All")
        self.filter_control.grid(row=0, column=0, sticky="w")

        export_row = ctk.CTkFrame(control_row, fg_color="transparent")
        export_row.grid(row=0, column=1, sticky="e")

        self.export_csv_button = ctk.CTkButton(
            export_row,
            text="Export CSV",
            width=100,
            state="disabled",
            command=self._handle_export_csv,
        )
        self.export_csv_button.grid(row=0, column=0, padx=(0, 8))

        self.export_json_button = ctk.CTkButton(
            export_row,
            text="Export JSON",
            width=100,
            state="disabled",
            command=self._handle_export_json,
        )
        self.export_json_button.grid(row=0, column=1)

    def _build_table(self) -> None:
        table_frame = ctk.CTkFrame(self, fg_color="transparent")
        table_frame.grid(row=2, column=0, sticky="nsew", padx=4, pady=(0, 4))
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:  # pragma: no cover - theme availability is platform-specific
            pass
        style.configure("SentinelLite.Treeview", rowheight=24)

        self.tree = ttk.Treeview(
            table_frame, columns=_COLUMNS, show="headings", style="SentinelLite.Treeview"
        )
        for column in _COLUMNS:
            self.tree.heading(column, text=_HEADINGS[column], command=lambda c=column: self._sort_by(c))
            width = 90 if column in ("status", "size") else 160
            self.tree.column(column, width=width, anchor="w")

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.tree.tag_configure("modified", foreground="#d97706")
        self.tree.tag_configure("new", foreground="#2563eb")
        self.tree.tag_configure("deleted", foreground="#dc2626")
        self.tree.tag_configure("unchanged", foreground="#16a34a")
        self.tree.tag_configure("error", foreground="#dc2626")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def results(self) -> list[ScanResult]:
        """The currently displayed results, unfiltered (a copy)."""
        return list(self._results)

    @property
    def timestamp(self) -> str:
        """The display timestamp passed to the most recent ``set_results`` call."""
        return self._timestamp

    def set_results(self, results: Iterable[ScanResult], timestamp: str = "") -> None:
        """Replace the displayed results and refresh the summary and table."""
        self._results = list(results)
        self._timestamp = timestamp
        self._sort_reverse.clear()

        summary = ScanSummary.from_results(self._results)
        self._summary_labels["Modified"].configure(text=f"Modified: {summary.modified}")
        self._summary_labels["New"].configure(text=f"New: {summary.new}")
        self._summary_labels["Deleted"].configure(text=f"Deleted: {summary.deleted}")
        self._summary_labels["Unchanged"].configure(text=f"Unchanged: {summary.unchanged}")
        self._summary_labels["Errors"].configure(text=f"Errors: {summary.errors}")

        export_state = "normal" if self._results else "disabled"
        self.export_csv_button.configure(state=export_state)
        self.export_json_button.configure(state=export_state)

        self._render_rows()

    def clear(self) -> None:
        """Reset to the empty, no-scan-yet state."""
        self.set_results([])

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _handle_export_csv(self) -> None:
        if self._export_csv_callback is not None:
            self._export_csv_callback()

    def _handle_export_json(self) -> None:
        if self._export_json_callback is not None:
            self._export_json_callback()

    # ------------------------------------------------------------------
    # Filtering / sorting / rendering
    # ------------------------------------------------------------------

    def _on_filter_changed(self, value: str) -> None:
        self._active_filter = value
        self._render_rows()

    def _visible_results(self) -> list[ScanResult]:
        if self._active_filter == "All":
            return self._results
        wanted_status = _FILTER_TO_STATUS[self._active_filter]
        return [result for result in self._results if result.status == wanted_status]

    def _render_rows(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for result in self._visible_results():
            self.tree.insert(
                "",
                "end",
                values=(
                    result.status.value,
                    result.path,
                    result.baseline_hash or "",
                    result.current_hash or "",
                    result.size if result.size is not None else "",
                    self._timestamp,
                ),
                tags=(_STATUS_TAG[result.status],),
            )

    def _sort_by(self, column: str) -> None:
        reverse = self._sort_reverse.get(column, False)
        index = _COLUMNS.index(column)

        def sort_key(result: ScanResult):
            return (
                result.status.value,
                result.path,
                result.baseline_hash or "",
                result.current_hash or "",
                result.size if result.size is not None else -1,
                self._timestamp,
            )[index]

        self._results.sort(key=sort_key, reverse=reverse)
        self._sort_reverse[column] = not reverse
        self._render_rows()
