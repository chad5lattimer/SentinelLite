"""Results display for SentinelLite: summary counts, filtering, and the
detailed results table.

Per PROJECT_SPEC.md section 12 (Results View). This module only renders
scan results computed elsewhere (``core.scanner``) -- it contains no
hashing or comparison logic of its own.

``filter_results`` is a pure function (no widget dependency) so the
filtering behavior is unit-testable on its own.
"""

from __future__ import annotations

from tkinter import ttk
from typing import Callable, Iterable, Sequence

import customtkinter as ctk

from core.models import ScanStatus
from core.scanner import ScanResult, ScanSummary

#: Filter options for the results table, in display order (section 12):
#: "All" plus one entry per possible ScanStatus.
FILTER_ALL = "All"
FILTER_OPTIONS: tuple[str, ...] = (
    FILTER_ALL,
    "Modified",
    "New",
    "Deleted",
    "Unchanged",
    "Errors",
)

_FILTER_TO_STATUS = {
    "Modified": ScanStatus.MODIFIED,
    "New": ScanStatus.NEW,
    "Deleted": ScanStatus.DELETED,
    "Unchanged": ScanStatus.UNCHANGED,
    "Errors": ScanStatus.ERROR,
}

#: Table columns, in display order (section 12).
_COLUMNS: tuple[str, ...] = ("status", "file", "baseline_hash", "current_hash", "size", "timestamp")
_HEADINGS = {
    "status": "Status",
    "file": "File",
    "baseline_hash": "Baseline Hash",
    "current_hash": "Current Hash",
    "size": "Size",
    "timestamp": "Timestamp",
}
_WIDTHS = {"status": 90, "file": 280, "baseline_hash": 130, "current_hash": 130, "size": 90, "timestamp": 160}


def filter_results(results: Sequence[ScanResult], filter_name: str) -> list[ScanResult]:
    """Return the subset of ``results`` matching ``filter_name``.

    ``filter_name`` must be one of ``FILTER_OPTIONS``; "All" returns every
    result, unchanged and in the same order. Pure function so the
    filtering behavior is unit-testable without building any widgets.
    """
    if filter_name == FILTER_ALL:
        return list(results)
    status = _FILTER_TO_STATUS.get(filter_name)
    if status is None:
        raise ValueError(f"Unknown filter: {filter_name!r}")
    return [result for result in results if result.status == status]


def _short_hash(value: str | None) -> str:
    """Shorten a hex digest for compact table display; ``None`` becomes "-"."""
    if not value:
        return "-"
    return value[:12] + "…"


def _row_sort_key(column: str, timestamp: str) -> Callable[[ScanResult], object]:
    if column == "status":
        return lambda result: result.status.value
    if column == "file":
        return lambda result: result.path
    if column == "baseline_hash":
        return lambda result: result.baseline_hash or ""
    if column == "current_hash":
        return lambda result: result.current_hash or ""
    if column == "size":
        return lambda result: result.size if result.size is not None else -1
    return lambda _result: timestamp


class ResultsView(ctk.CTkFrame):
    """Summary statistics, a status filter, and the detailed results table."""

    def __init__(self, master) -> None:
        super().__init__(master)
        self._results: list[ScanResult] = []
        self._timestamp = "-"
        self._active_filter = FILTER_ALL
        self._sort_column: str | None = None
        self._sort_reverse = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_summary()
        self._build_filter()
        self._build_table()

    def _build_summary(self) -> None:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 8))

        self.summary_labels: dict[str, ctk.CTkLabel] = {}
        for index, name in enumerate(("Modified", "New", "Deleted", "Unchanged", "Errors")):
            label = ctk.CTkLabel(frame, text=f"{name}: 0", font=ctk.CTkFont(weight="bold"))
            label.grid(row=0, column=index, padx=10, sticky="w")
            self.summary_labels[name] = label

    def _build_filter(self) -> None:
        self.filter_var = ctk.StringVar(value=FILTER_ALL)
        self.filter_control = ctk.CTkSegmentedButton(
            self,
            values=list(FILTER_OPTIONS),
            variable=self.filter_var,
            command=self._on_filter_changed,
        )
        self.filter_control.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 8))

    def _build_table(self) -> None:
        self.table = ttk.Treeview(self, columns=_COLUMNS, show="headings", selectmode="browse")
        for column in _COLUMNS:
            self.table.heading(column, text=_HEADINGS[column], command=lambda c=column: self._sort_by(c))
            self.table.column(column, width=_WIDTHS[column], anchor="w")

        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)

        self.table.grid(row=2, column=0, sticky="nsew", padx=(4, 0), pady=(0, 4))
        scrollbar.grid(row=2, column=1, sticky="ns", pady=(0, 4))

    def set_results(self, results: Iterable[ScanResult], timestamp: str = "-") -> None:
        """Replace the displayed results and refresh the summary/table."""
        self._results = list(results)
        self._timestamp = timestamp
        self._refresh_summary()
        self._render_table()

    def clear(self) -> None:
        """Reset the view to its empty, no-scan-yet state."""
        self.set_results([], timestamp="-")

    def _refresh_summary(self) -> None:
        summary = ScanSummary.from_results(self._results)
        self.summary_labels["Modified"].configure(text=f"Modified: {summary.modified}")
        self.summary_labels["New"].configure(text=f"New: {summary.new}")
        self.summary_labels["Deleted"].configure(text=f"Deleted: {summary.deleted}")
        self.summary_labels["Unchanged"].configure(text=f"Unchanged: {summary.unchanged}")
        self.summary_labels["Errors"].configure(text=f"Errors: {summary.errors}")

    def _on_filter_changed(self, value: str) -> None:
        self._active_filter = value
        self._render_table()

    def _sort_by(self, column: str) -> None:
        self._sort_reverse = not self._sort_reverse if self._sort_column == column else False
        self._sort_column = column
        self._render_table()

    def _render_table(self) -> None:
        for row in self.table.get_children():
            self.table.delete(row)

        visible = filter_results(self._results, self._active_filter)
        if self._sort_column:
            visible = sorted(
                visible, key=_row_sort_key(self._sort_column, self._timestamp), reverse=self._sort_reverse
            )

        for result in visible:
            self.table.insert(
                "",
                "end",
                values=(
                    result.status.value,
                    result.path,
                    _short_hash(result.baseline_hash),
                    _short_hash(result.current_hash),
                    result.size if result.size is not None else "-",
                    self._timestamp,
                ),
            )
