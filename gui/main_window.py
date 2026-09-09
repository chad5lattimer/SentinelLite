"""Main application window for SentinelLite.

Run 5 scope: wires the CustomTkinter shell built in Run 1 to the core
engine (``core.baseline`` / ``core.scanner``, Runs 2-4) through the
storage layer (``storage.database`` / ``storage.repository``, Run 3).

This module handles presentation and coordination only -- per
PROJECT_SPEC.md section 5 ("The GUI must not contain hashing or
filesystem comparison logic"), it never hashes files or compares
filesystem state itself; it always delegates to ``core``.

Long-running work (creating a baseline, running a scan) happens on a
background thread so the Tk event loop is never blocked (section 13:
"Do not perform a large filesystem scan directly on the GUI event loop").
Worker threads never touch Tk widgets directly -- they schedule updates
back onto the GUI thread via ``self.after(...)``.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import customtkinter as ctk

from config import APP_DESCRIPTION, APP_NAME, PATHS
from core.baseline import (
    Baseline,
    create_baseline,
    find_baseline_for_directory,
    save_baseline,
)
from core.models import ScanStatus
from core.scanner import ScanResult, run_scan, save_scan
from gui import dialogs
from gui.history_view import ScanHistoryDialog
from gui.results_view import ResultsView
from reports.exporter import export_csv, export_json
from storage.database import connect as connect_db
from storage.database import get_connection

logger = logging.getLogger(__name__)

#: Minimum time between progress-bar updates while a background scan or
#: baseline creation is running, so a directory with many files does not
#: flood the Tk event loop with ``after`` calls (PROJECT_SPEC.md section 34:
#: "The exact progress calculation may be approximate if necessary").
_PROGRESS_UPDATE_INTERVAL_SECONDS = 0.1


def _format_display_time(iso_timestamp: str) -> str:
    """Render an ISO-8601 timestamp as a friendly string, e.g. "Aug 26, 2026 12:31 AM"."""
    try:
        parsed = datetime.fromisoformat(iso_timestamp)
    except ValueError:
        return iso_timestamp
    return parsed.strftime("%b %d, %Y %I:%M %p")


class MainWindow(ctk.CTk):
    """Top-level application window.

    Owns the monitored directory and active baseline state (GUI state
    transitions follow PROJECT_SPEC.md section 24), plus the SQLite
    database path.

    ``self._connection`` is opened once and used only from the GUI/main
    thread (e.g. looking up a baseline when a folder is selected).
    Background workers never touch it -- sqlite3 connections cannot be
    shared across threads (``check_same_thread`` defaults to ``True`` for
    good reason), so each background task opens its own short-lived
    connection to the same database file via ``_open_worker_connection``.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        super().__init__()

        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        self.title(f"{APP_NAME} - {APP_DESCRIPTION}")
        self.geometry("900x680")
        self.minsize(760, 560)

        self._directory: Path | None = None
        self._baseline: Baseline | None = None
        self._scan_in_progress = False

        # The most recently displayed scan (either just-completed or
        # reloaded from history via Scan History), kept so Export CSV/JSON
        # know what to write (PROJECT_SPEC.md section 15).
        self._last_scan_id: int | None = None
        self._last_scan_results: list[ScanResult] = []
        self._last_scan_timestamp: str = ""

        PATHS.ensure_directories()
        self._db_path: Path = db_path or PATHS.database_path
        self._connection: sqlite3.Connection = get_connection(self._db_path)

        self._build_layout()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(6, weight=1)

        self._build_header()
        self._build_directory_section()
        self._build_baseline_section()
        self._build_scan_section()
        self._build_reports_section()
        self._build_progress_section()
        self._build_results_section()
        self._build_status_section()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header, text=APP_NAME, font=ctk.CTkFont(size=24, weight="bold")
        ).grid(row=0, column=0, padx=20, pady=(16, 0), sticky="w")

        ctk.CTkLabel(
            header,
            text=APP_DESCRIPTION,
            font=ctk.CTkFont(size=13),
            text_color=("gray40", "gray70"),
        ).grid(row=1, column=0, padx=20, pady=(0, 16), sticky="w")

    def _build_directory_section(self) -> None:
        section = ctk.CTkFrame(self)
        section.grid(row=1, column=0, padx=20, pady=(10, 10), sticky="ew")
        section.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            section, text="Monitored Directory", font=ctk.CTkFont(size=15, weight="bold")
        ).grid(row=0, column=0, padx=16, pady=(12, 4), sticky="w")

        self.directory_value_label = ctk.CTkLabel(section, text="No folder selected.", anchor="w")
        self.directory_value_label.grid(row=1, column=0, padx=16, pady=(0, 12), sticky="w")

        self.change_folder_button = ctk.CTkButton(
            section, text="Change Folder", command=self._on_change_folder
        )
        self.change_folder_button.grid(row=1, column=1, padx=16, pady=(0, 12), sticky="e")

    def _build_baseline_section(self) -> None:
        section = ctk.CTkFrame(self)
        section.grid(row=2, column=0, padx=20, pady=(0, 10), sticky="ew")
        section.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            section, text="Baseline", font=ctk.CTkFont(size=15, weight="bold")
        ).grid(row=0, column=0, padx=16, pady=(12, 4), sticky="w")

        self.baseline_status_label = ctk.CTkLabel(
            section,
            text="No baseline exists. Create a baseline before scanning.",
            anchor="w",
            justify="left",
        )
        self.baseline_status_label.grid(row=1, column=0, padx=16, pady=(0, 12), sticky="w")

        self.create_baseline_button = ctk.CTkButton(
            section, text="Create Baseline", state="disabled", command=self._on_create_baseline
        )
        self.create_baseline_button.grid(row=1, column=1, padx=16, pady=(0, 12), sticky="e")

    def _build_scan_section(self) -> None:
        section = ctk.CTkFrame(self)
        section.grid(row=3, column=0, padx=20, pady=(0, 10), sticky="ew")
        section.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            section, text="Scan", font=ctk.CTkFont(size=15, weight="bold")
        ).grid(row=0, column=0, padx=16, pady=(12, 4), sticky="w")

        self.last_scan_label = ctk.CTkLabel(section, text="Last scan: never", anchor="w")
        self.last_scan_label.grid(row=1, column=0, padx=16, pady=(0, 12), sticky="w")

        self.scan_now_button = ctk.CTkButton(
            section, text="Scan Now", state="disabled", command=self._on_scan_now
        )
        self.scan_now_button.grid(row=1, column=1, padx=16, pady=(0, 12), sticky="e")

    def _build_reports_section(self) -> None:
        section = ctk.CTkFrame(self)
        section.grid(row=4, column=0, padx=20, pady=(0, 10), sticky="ew")
        section.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            section, text="Reports", font=ctk.CTkFont(size=15, weight="bold")
        ).grid(row=0, column=0, padx=16, pady=(12, 4), sticky="w", columnspan=2)

        self.reports_hint_label = ctk.CTkLabel(
            section, text="Export the last scan, or review past scans.", anchor="w"
        )
        self.reports_hint_label.grid(row=1, column=0, padx=16, pady=(0, 12), sticky="w")

        button_row = ctk.CTkFrame(section, fg_color="transparent")
        button_row.grid(row=1, column=1, padx=16, pady=(0, 12), sticky="e")

        self.export_csv_button = ctk.CTkButton(
            button_row, text="Export CSV", state="disabled", command=self._on_export_csv
        )
        self.export_csv_button.grid(row=0, column=0, padx=(0, 8))

        self.export_json_button = ctk.CTkButton(
            button_row, text="Export JSON", state="disabled", command=self._on_export_json
        )
        self.export_json_button.grid(row=0, column=1, padx=(0, 8))

        self.scan_history_button = ctk.CTkButton(
            button_row, text="Scan History", state="disabled", command=self._on_view_history
        )
        self.scan_history_button.grid(row=0, column=2)

    def _build_progress_section(self) -> None:
        section = ctk.CTkFrame(self)
        section.grid(row=5, column=0, padx=20, pady=(0, 10), sticky="ew")
        section.grid_columnconfigure(0, weight=1)
        self._progress_section = section

        self.progress_label = ctk.CTkLabel(section, text="Scanning...", anchor="w")
        self.progress_label.grid(row=0, column=0, padx=16, pady=(12, 4), sticky="w")

        # Total file counts are not known ahead of time without a second,
        # wasted directory walk, so progress is shown as an indeterminate
        # animation plus a running "files processed" count -- an accepted
        # approximation per PROJECT_SPEC.md section 13.
        self.progress_bar = ctk.CTkProgressBar(section, mode="indeterminate")
        self.progress_bar.grid(row=1, column=0, padx=16, pady=(0, 4), sticky="ew")

        self.progress_detail_label = ctk.CTkLabel(
            section, text="", anchor="w", justify="left", text_color=("gray40", "gray70")
        )
        self.progress_detail_label.grid(row=2, column=0, padx=16, pady=(0, 12), sticky="w")

        section.grid_remove()  # hidden until a scan/baseline creation starts

    def _build_results_section(self) -> None:
        self.results_view = ResultsView(self)
        self.results_view.grid(row=6, column=0, padx=20, pady=(0, 10), sticky="nsew")

    def _build_status_section(self) -> None:
        section = ctk.CTkFrame(self)
        section.grid(row=7, column=0, padx=20, pady=(0, 20), sticky="ew")
        section.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(
            section,
            text="Select a folder to begin.",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.status_label.grid(row=0, column=0, padx=16, pady=16)

    # ------------------------------------------------------------------
    # Folder selection
    # ------------------------------------------------------------------

    def _on_change_folder(self) -> None:
        if self._scan_in_progress:
            return
        chosen = dialogs.choose_directory(
            self, initial_dir=str(self._directory) if self._directory else None
        )
        if not chosen:
            return
        self._set_directory(Path(chosen))

    def _set_directory(self, directory: Path) -> None:
        """Select a monitored directory and refresh dependent state.

        Exposed as its own method (rather than folded into the dialog
        callback) so tests can drive the workflow without a real folder
        picker.
        """
        self._directory = Path(directory).resolve()
        self.directory_value_label.configure(text=str(self._directory))
        self.create_baseline_button.configure(state="normal")

        self._baseline = find_baseline_for_directory(self._connection, self._directory)
        self.results_view.clear()
        self.last_scan_label.configure(text="Last scan: never")
        self._clear_last_scan()

        if self._baseline is not None:
            self._show_baseline_ready(self._baseline)
            self.scan_now_button.configure(state="normal")
            self.scan_history_button.configure(state="normal")
            self.status_label.configure(text="Baseline Ready")
        else:
            self.baseline_status_label.configure(
                text="No baseline exists. Create a baseline before scanning."
            )
            self.scan_now_button.configure(state="disabled")
            self.scan_history_button.configure(state="disabled")
            self.status_label.configure(text="No baseline exists. Create a baseline before scanning.")

    def _show_baseline_ready(self, baseline: Baseline) -> None:
        self.baseline_status_label.configure(
            text=(
                "Status: Ready\n"
                f"Created: {_format_display_time(baseline.created_at)}\n"
                f"Files: {baseline.file_count:,}"
            )
        )

    # ------------------------------------------------------------------
    # Baseline creation
    # ------------------------------------------------------------------

    def _on_create_baseline(self) -> None:
        if self._directory is None or self._scan_in_progress:
            return
        if self._baseline is not None and not dialogs.confirm_replace_baseline(self):
            return

        self._start_background_task(
            label="Creating Baseline...",
            worker=self._create_baseline_worker,
            on_success=self._on_baseline_created,
            on_error=self._on_baseline_error,
        )

    def _create_baseline_worker(self, progress_callback) -> Baseline:
        baseline, errors = create_baseline(self._directory, progress_callback=progress_callback)
        if errors:
            logger.warning(
                "Baseline for %s excludes %d unreadable file(s).", self._directory, len(errors)
            )
        # Runs on a background thread -- open a connection scoped to this
        # call rather than sharing self._connection (see class docstring).
        with connect_db(self._db_path) as worker_connection:
            return save_baseline(worker_connection, baseline)

    def _on_baseline_created(self, baseline: Baseline) -> None:
        self._baseline = baseline
        self._show_baseline_ready(baseline)
        self.scan_now_button.configure(state="normal")
        self.scan_history_button.configure(state="normal")
        self.results_view.clear()
        self._clear_last_scan()
        self.last_scan_label.configure(text="Last scan: never")
        self.status_label.configure(text="Baseline Ready")
        dialogs.show_info(
            self,
            "Baseline Created",
            (
                f"Directory:\n{baseline.root_directory}\n\n"
                f"Files:\n{baseline.file_count:,}\n\n"
                f"Created:\n{_format_display_time(baseline.created_at)}\n\n"
                "Status:\n✓ Baseline Ready"
            ),
        )

    def _on_baseline_error(self, error: Exception) -> None:
        # This runs on the GUI thread via `after`, well outside the
        # worker's `except` block, so `sys.exc_info()` is empty here --
        # `logger.exception()` would silently log "NoneType: None". Pass
        # the caught error explicitly via `exc_info` instead.
        logger.error("Baseline creation failed for %s.", self._directory, exc_info=error)
        self.status_label.configure(text="The application encountered an unexpected error.")
        dialogs.show_error(
            self,
            "Unable to Create Baseline",
            (
                f"The application could not create a baseline for:\n\n{self._directory}\n\n"
                "Check the application log for details."
            ),
        )

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------

    def _on_scan_now(self) -> None:
        if self._baseline is None or self._scan_in_progress:
            return

        self._start_background_task(
            label="Scanning...",
            worker=self._run_scan_worker,
            on_success=self._on_scan_complete,
            on_error=self._on_scan_error,
        )

    def _run_scan_worker(self, progress_callback) -> tuple[list[ScanResult], str, int]:
        started_at = datetime.now(timezone.utc).isoformat()
        results = run_scan(self._baseline, progress_callback=progress_callback)
        completed_at = datetime.now(timezone.utc).isoformat()
        # Runs on a background thread -- open a connection scoped to this
        # call rather than sharing self._connection (see class docstring).
        with connect_db(self._db_path) as worker_connection:
            scan_id = save_scan(
                worker_connection,
                baseline_id=self._baseline.baseline_id,
                started_at=started_at,
                results=results,
                completed_at=completed_at,
            )
        return results, completed_at, scan_id

    def _on_scan_complete(self, outcome: tuple[list[ScanResult], str, int]) -> None:
        results, completed_at, scan_id = outcome
        display_time = _format_display_time(completed_at)
        self.results_view.set_results(results, timestamp=display_time)
        self.last_scan_label.configure(text=f"Last scan: {display_time}")
        self._set_last_scan(scan_id=scan_id, results=results, timestamp=display_time)

        has_errors = any(result.status == ScanStatus.ERROR for result in results)
        has_changes = any(
            result.status in (ScanStatus.MODIFIED, ScanStatus.NEW, ScanStatus.DELETED)
            for result in results
        )
        if has_errors:
            self.status_label.configure(text="⚠ Scan Completed With Errors")
        elif has_changes:
            self.status_label.configure(text="⚠ Changes Detected")
        else:
            self.status_label.configure(text="✓ No Changes Detected")

    def _on_scan_error(self, error: Exception) -> None:
        directory = self._baseline.root_directory if self._baseline else "the monitored directory"
        # See the comment in `_on_baseline_error` -- this also runs outside
        # the original `except` block, so pass `error` via `exc_info`.
        logger.error("Scan failed for %s.", directory, exc_info=error)
        self.status_label.configure(text="✕ Scan Error")
        dialogs.show_error(
            self,
            "Scan Error",
            (
                f"The application could not complete a scan of:\n\n{directory}\n\n"
                "Check the application log for details."
            ),
        )

    # ------------------------------------------------------------------
    # Reports: export and scan history (PROJECT_SPEC.md section 30 - Run 6)
    # ------------------------------------------------------------------

    def _clear_last_scan(self) -> None:
        self._last_scan_id = None
        self._last_scan_results = []
        self._last_scan_timestamp = ""
        self.export_csv_button.configure(state="disabled")
        self.export_json_button.configure(state="disabled")

    def _set_last_scan(self, *, scan_id: int | None, results: list[ScanResult], timestamp: str) -> None:
        self._last_scan_id = scan_id
        self._last_scan_results = results
        self._last_scan_timestamp = timestamp
        self.export_csv_button.configure(state="normal")
        # JSON export needs a scan_id (PROJECT_SPEC.md section 15.2); a scan
        # loaded from a future in-memory-only source could lack one, so
        # guard rather than assume every caller has one.
        self.export_json_button.configure(state="normal" if scan_id is not None else "disabled")

    def _on_export_csv(self) -> None:
        if not self._last_scan_results:
            return
        destination = dialogs.choose_save_file(
            self, default_name="sentinellite_scan.csv", extension=".csv", file_description="CSV Files"
        )
        if not destination:
            return
        try:
            export_csv(self._last_scan_results, Path(destination), timestamp=self._last_scan_timestamp)
        except OSError as error:
            logger.error("CSV export to %s failed.", destination, exc_info=error)
            dialogs.show_error(
                self,
                "Export Failed",
                f"The application could not write the export file:\n\n{destination}",
            )
            return
        dialogs.show_info(self, "Export Complete", f"Results exported to:\n\n{destination}")

    def _on_export_json(self) -> None:
        if not self._last_scan_results or self._last_scan_id is None:
            return
        destination = dialogs.choose_save_file(
            self, default_name="sentinellite_scan.json", extension=".json", file_description="JSON Files"
        )
        if not destination:
            return
        root_directory = self._baseline.root_directory if self._baseline else str(self._directory or "")
        try:
            export_json(
                self._last_scan_results,
                Path(destination),
                scan_id=self._last_scan_id,
                timestamp=self._last_scan_timestamp,
                root_directory=root_directory,
            )
        except OSError as error:
            logger.error("JSON export to %s failed.", destination, exc_info=error)
            dialogs.show_error(
                self,
                "Export Failed",
                f"The application could not write the export file:\n\n{destination}",
            )
            return
        dialogs.show_info(self, "Export Complete", f"Results exported to:\n\n{destination}")

    def _on_view_history(self) -> None:
        if self._baseline is None:
            return
        ScanHistoryDialog(
            self,
            self._connection,
            self._baseline.baseline_id,
            on_view_results=self._on_history_results_selected,
            on_export=self._on_history_export_selected,
        )

    def _on_history_results_selected(self, results: list[ScanResult], display_timestamp: str) -> None:
        self.results_view.set_results(results, timestamp=display_timestamp)

    def _on_history_export_selected(
        self, file_format: str, scan_id: int, results: list[ScanResult], display_timestamp: str
    ) -> None:
        # Route through the same export handlers used for the just-completed
        # scan, so a past scan can be exported without first "viewing" it.
        self._set_last_scan(scan_id=scan_id, results=results, timestamp=display_timestamp)
        if file_format == "csv":
            self._on_export_csv()
        else:
            self._on_export_json()

    # ------------------------------------------------------------------
    # Background task plumbing
    # ------------------------------------------------------------------

    def _start_background_task(
        self,
        *,
        label: str,
        worker: Callable[[Callable[[int, str], None]], object],
        on_success: Callable[[object], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        """Run ``worker`` on a background thread, keeping the GUI responsive.

        ``worker`` receives a progress callback and returns a result that is
        handed to ``on_success`` back on the GUI thread; any exception is
        handed to ``on_error`` instead. Neither callback nor ``worker``'s
        progress callback ever touches Tk widgets from the worker thread
        itself -- updates are marshalled via ``self.after``.
        """
        self._scan_in_progress = True
        self._set_controls_enabled(False)
        self.progress_label.configure(text=label)
        self.progress_detail_label.configure(text="")
        self._progress_section.grid()
        self.progress_bar.start()

        last_update = [0.0]

        def progress_callback(processed: int, current_path: str) -> None:
            now = time.monotonic()
            if now - last_update[0] < _PROGRESS_UPDATE_INTERVAL_SECONDS:
                return
            last_update[0] = now
            self.after(0, lambda: self._update_progress(processed, current_path))

        def run() -> None:
            try:
                result = worker(progress_callback)
            except Exception as caught:  # noqa: BLE001 - surfaced to the user, never swallowed
                # Python implicitly deletes the `except ... as name` binding
                # when the except block exits, so it must be copied to a
                # plain variable here -- otherwise the lambda below raises
                # NameError once `self.after` actually invokes it.
                failure = caught
                self.after(0, lambda: self._finish_background_task(on_error, failure))
            else:
                self.after(0, lambda: self._finish_background_task(on_success, result))

        threading.Thread(target=run, daemon=True).start()

    def _update_progress(self, processed: int, current_path: str) -> None:
        self.progress_detail_label.configure(
            text=f"Files processed: {processed:,}\nCurrent file: {current_path}"
        )

    def _finish_background_task(self, callback: Callable[[object], None], payload: object) -> None:
        self._scan_in_progress = False
        self.progress_bar.stop()
        self._progress_section.grid_remove()
        self._set_controls_enabled(True)
        callback(payload)

    def _set_controls_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.change_folder_button.configure(state=state)
        self.create_baseline_button.configure(
            state=state if self._directory is not None else "disabled"
        )
        self.scan_now_button.configure(state=state if self._baseline is not None else "disabled")
        self.scan_history_button.configure(state=state if self._baseline is not None else "disabled")
        self.export_csv_button.configure(
            state=state if self._last_scan_results else "disabled"
        )
        self.export_json_button.configure(
            state=state if self._last_scan_results and self._last_scan_id is not None else "disabled"
        )

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def _on_close(self) -> None:
        try:
            self._connection.close()
        finally:
            self.destroy()
