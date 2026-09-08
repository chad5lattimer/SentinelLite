"""Main application window for SentinelLite.

Run 5 scope (PROJECT_SPEC.md section 30): wires the core engine
(``core.baseline``, ``core.scanner``) and storage layer
(``storage.database``) into the CustomTkinter UI built in Run 1 --
folder selection, baseline creation (with the accidental-replacement
confirmation from section 9), running a scan, a background worker thread
so the GUI never blocks (section 13), progress display, summary
statistics, and a filterable results table (``gui.results_view``).

This module must stay free of security/core logic (section 5): it only
calls into ``core``/``storage`` and renders what comes back. All hashing,
filesystem, and comparison logic lives in ``core``.
"""

from __future__ import annotations

import logging
import queue
import threading
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog
from typing import Any, Callable

import customtkinter as ctk

from config import APP_DESCRIPTION, APP_NAME, PATHS
from core.baseline import Baseline, BaselineNotFoundError, create_baseline, load_baseline, save_baseline
from core.filesystem import ProgressCallback
from core.scanner import ScanSummary, get_scan_results, list_scans, run_scan, save_scan
from gui import dialogs
from gui.results_view import ResultsView
from storage.database import DatabaseCorruptedError, get_connection

logger = logging.getLogger(__name__)

#: How often (ms) the GUI thread polls a background worker's progress
#: queue. Short enough to feel live, long enough not to busy-loop.
_POLL_INTERVAL_MS = 80

# Status-label colors: (light mode, dark mode), per CTk convention.
_NEUTRAL_COLOR = ("gray20", "gray90")
_SUCCESS_COLOR = ("#1a7f37", "#3fb950")
_WARNING_COLOR = ("#9a6700", "#d29922")
_ERROR_COLOR = ("#cf222e", "#f85149")


def _format_timestamp(value: str | None) -> str:
    """Format an ISO-8601 timestamp for display, in the local timezone.

    Falls back to the raw value if it cannot be parsed (e.g. ``None``),
    rather than raising -- this is a display helper, not a validator.
    """
    if not value:
        return "-"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    return parsed.astimezone().strftime("%b %d, %Y %I:%M %p")


def _friendly_error(error: Exception) -> str:
    """Translate an exception into a plain-language message (section 18).

    Technical details are logged separately; this text is what the user
    sees, so it must never be a raw traceback.
    """
    if isinstance(error, NotADirectoryError):
        return (
            "The monitored folder could not be found. It may have been "
            "moved, renamed, or deleted.\n\nSelect a folder and try again."
        )
    if isinstance(error, DatabaseCorruptedError):
        return (
            "The local SentinelLite database could not be read. It may be "
            "corrupted.\n\nCheck the application log for details."
        )
    if isinstance(error, OSError):
        return f"A filesystem error occurred:\n{error.strerror or error}"
    return "An unexpected error occurred. Check the application log for details."


class MainWindow(ctk.CTk):
    """Top-level application window.

    Owns the database connection and the current in-memory baseline for
    this session, and coordinates background workers for baseline
    creation and scanning so the GUI event loop is never blocked by
    filesystem I/O or hashing.
    """

    def __init__(self) -> None:
        super().__init__()

        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        self.title(f"{APP_NAME} - {APP_DESCRIPTION}")
        self.geometry("900x700")
        self.minsize(760, 560)

        self.selected_directory: Path | None = None
        self.current_baseline: Baseline | None = None
        self.connection = None
        self._scan_started_at: str | None = None

        self._build_layout()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._open_database()
        if self.connection is not None:
            self._try_restore_latest_baseline()
            self._update_controls()

    # -- Layout ------------------------------------------------------------

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(6, weight=1)

        self._build_header()
        self._build_directory_section()
        self._build_baseline_section()
        self._build_scan_section()
        self._build_progress_section()
        self._build_status_section()
        self._build_results_section()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        title_label = ctk.CTkLabel(
            header,
            text=APP_NAME,
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        title_label.grid(row=0, column=0, padx=20, pady=(16, 0), sticky="w")

        subtitle_label = ctk.CTkLabel(
            header,
            text=APP_DESCRIPTION,
            font=ctk.CTkFont(size=13),
            text_color=("gray40", "gray70"),
        )
        subtitle_label.grid(row=1, column=0, padx=20, pady=(0, 16), sticky="w")

    def _build_directory_section(self) -> None:
        section = ctk.CTkFrame(self)
        section.grid(row=1, column=0, padx=20, pady=(10, 10), sticky="ew")
        section.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            section, text="Monitored Directory", font=ctk.CTkFont(size=15, weight="bold")
        ).grid(row=0, column=0, padx=16, pady=(12, 4), sticky="w")

        self.directory_value_label = ctk.CTkLabel(
            section, text="No folder selected.", anchor="w"
        )
        self.directory_value_label.grid(row=1, column=0, padx=16, pady=(0, 12), sticky="w")

        self.change_folder_button = ctk.CTkButton(
            section, text="Change Folder", state="disabled", command=self._on_change_folder
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

    def _build_progress_section(self) -> None:
        # Hidden until a background operation (baseline creation or scan)
        # starts -- see _run_worker / _finish_worker. Per PROJECT_SPEC.md
        # section 13, the exact progress calculation may be approximate;
        # an indeterminate bar plus a live processed-file counter avoids
        # a second, throwaway enumeration pass just to compute a total.
        self.progress_frame = ctk.CTkFrame(self)
        self.progress_frame.grid(row=4, column=0, padx=20, pady=(0, 10), sticky="ew")
        self.progress_frame.grid_columnconfigure(0, weight=1)
        self.progress_frame.grid_remove()

        self.progress_bar = ctk.CTkProgressBar(self.progress_frame, mode="indeterminate")
        self.progress_bar.grid(row=0, column=0, padx=16, pady=(12, 4), sticky="ew")

        self.progress_count_label = ctk.CTkLabel(self.progress_frame, text="", anchor="w")
        self.progress_count_label.grid(row=1, column=0, padx=16, sticky="w")

        self.progress_file_label = ctk.CTkLabel(self.progress_frame, text="", anchor="w")
        self.progress_file_label.grid(row=2, column=0, padx=16, pady=(0, 12), sticky="w")

    def _build_status_section(self) -> None:
        section = ctk.CTkFrame(self)
        section.grid(row=5, column=0, padx=20, pady=(0, 10), sticky="ew")
        section.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(
            section,
            text="Select a folder to begin.",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.status_label.grid(row=0, column=0, padx=16, pady=16)

    def _build_results_section(self) -> None:
        self.results_view = ResultsView(self)
        self.results_view.grid(row=6, column=0, padx=20, pady=(0, 20), sticky="nsew")

    # -- Startup / shutdown --------------------------------------------------

    def _open_database(self) -> None:
        try:
            PATHS.ensure_directories()
            self.connection = get_connection(PATHS.database_path)
        except DatabaseCorruptedError as error:
            logger.error("Could not open the database: %s", error)
            self.connection = None
            self._set_status(
                "The application encountered an unexpected error. Check the application log for details.",
                _ERROR_COLOR,
            )
            dialogs.show_error(self, "Database Error", _friendly_error(error))

    def _try_restore_latest_baseline(self) -> None:
        """Re-load the most recent baseline on startup, if one exists.

        This lets "Baseline Ready" / last-scan information survive an
        application restart rather than forcing the user to recreate a
        baseline every launch (section 24: "Baseline exists").
        """
        try:
            self.current_baseline = load_baseline(self.connection)
        except BaselineNotFoundError:
            self.current_baseline = None
            return

        self.selected_directory = Path(self.current_baseline.root_directory)
        self._set_status("Baseline Ready", _NEUTRAL_COLOR)

        scans = list_scans(self.connection, baseline_id=self.current_baseline.baseline_id)
        if scans:
            latest = scans[0]
            results = get_scan_results(self.connection, latest.scan_id)
            completed_display = _format_timestamp(latest.completed_at or latest.started_at)
            self.last_scan_label.configure(text=f"Last scan: {completed_display}")
            self.results_view.set_results(results, timestamp=completed_display)

    def _on_close(self) -> None:
        if self.connection is not None:
            self.connection.close()
        self.destroy()

    # -- State / control refresh ---------------------------------------------

    def _update_controls(self) -> None:
        """Sync button enabled-state and the directory/baseline text to
        the current selection, per the application states in section 24."""
        have_db = self.connection is not None

        self.change_folder_button.configure(state="normal" if have_db else "disabled")
        self.create_baseline_button.configure(
            state="normal" if (have_db and self.selected_directory is not None) else "disabled"
        )
        self.scan_now_button.configure(
            state="normal" if (have_db and self.current_baseline is not None) else "disabled"
        )

        self.directory_value_label.configure(
            text=str(self.selected_directory) if self.selected_directory is not None else "No folder selected."
        )

        if self.current_baseline is not None:
            created_display = _format_timestamp(self.current_baseline.created_at)
            self.baseline_status_label.configure(
                text=(
                    f"Status: Ready Created: {created_display} "
                    f"Files: {self.current_baseline.file_count:,}"
                )
            )
        else:
            self.baseline_status_label.configure(
                text="No baseline exists. Create a baseline before scanning."
            )

    def _set_status(self, text: str, color) -> None:
        self.status_label.configure(text=text, text_color=color)

    def _set_controls_enabled(self, enabled: bool) -> None:
        if enabled:
            self._update_controls()
        else:
            self.change_folder_button.configure(state="disabled")
            self.create_baseline_button.configure(state="disabled")
            self.scan_now_button.configure(state="disabled")

    # -- Folder selection -----------------------------------------------------

    def _on_change_folder(self) -> None:
        chosen = filedialog.askdirectory(parent=self, mustexist=True, title="Select a folder to monitor")
        if not chosen:
            return

        new_directory = Path(chosen)
        # A baseline is tied to one root directory (core.scanner.run_scan
        # always re-scans baseline.root_directory), so switching to a
        # different, not-yet-baselined folder must not leave "Scan Now"
        # pointed at the old folder's baseline.
        if self.current_baseline is not None and Path(self.current_baseline.root_directory) != new_directory:
            self.current_baseline = None
            self.results_view.clear()
            self.last_scan_label.configure(text="Last scan: never")

        self.selected_directory = new_directory
        self._update_controls()
        if self.current_baseline is None:
            self._set_status("No baseline exists. Create a baseline before scanning.", _NEUTRAL_COLOR)
        else:
            self._set_status("Baseline Ready", _NEUTRAL_COLOR)

    # -- Baseline creation -----------------------------------------------------

    def _on_create_baseline(self) -> None:
        if self.selected_directory is None or self.connection is None:
            return

        if self.current_baseline is not None:
            confirmed = dialogs.confirm_replace_baseline(
                self, self.current_baseline.root_directory, self.current_baseline.file_count
            )
            if not confirmed:
                return

        self._run_worker(
            target=self._create_baseline_worker,
            busy_text="Creating baseline...",
            on_done=self._on_baseline_worker_done,
        )

    def _create_baseline_worker(self, progress_callback: ProgressCallback) -> tuple[Baseline, list]:
        baseline, errors = create_baseline(self.selected_directory, progress_callback=progress_callback)
        # A sqlite3 connection may only be used from the thread that
        # created it; self.connection belongs to the GUI thread, so this
        # background thread opens (and closes) its own connection to the
        # same database file rather than sharing it.
        connection = get_connection(PATHS.database_path)
        try:
            saved = save_baseline(connection, baseline)
        finally:
            connection.close()
        return saved, errors

    def _on_baseline_worker_done(self, result: Any, error: Exception | None) -> None:
        if error is not None:
            logger.exception("Baseline creation failed.", exc_info=error)
            self._set_status("No baseline exists. Create a baseline before scanning.", _NEUTRAL_COLOR)
            dialogs.show_error(self, "Could Not Create Baseline", _friendly_error(error))
            return

        baseline, errors = result
        self.current_baseline = baseline
        self.results_view.clear()
        self.last_scan_label.configure(text="Last scan: never")
        self._update_controls()
        self._set_status("Baseline Ready", _NEUTRAL_COLOR)

        dialogs.show_baseline_created(
            self, baseline.root_directory, baseline.file_count, _format_timestamp(baseline.created_at)
        )
        if errors:
            dialogs.show_warning(
                self,
                "Some Files Were Skipped",
                f"{len(errors)} file(s) could not be read and were excluded from the "
                "baseline.\n\nSee the application log for details.",
            )

    # -- Scanning -----------------------------------------------------------

    def _on_scan_now(self) -> None:
        if self.current_baseline is None or self.connection is None:
            return

        self._scan_started_at = datetime.now(timezone.utc).isoformat()
        self._run_worker(
            target=self._run_scan_worker,
            busy_text="Scanning...",
            on_done=self._on_scan_worker_done,
        )

    def _run_scan_worker(self, progress_callback: ProgressCallback) -> tuple[int, list, ScanSummary]:
        baseline = self.current_baseline
        assert baseline is not None and baseline.baseline_id is not None
        results = run_scan(baseline, progress_callback=progress_callback)
        # See _create_baseline_worker: a fresh connection for this thread.
        connection = get_connection(PATHS.database_path)
        try:
            scan_id = save_scan(connection, baseline.baseline_id, self._scan_started_at, results)
        finally:
            connection.close()
        return scan_id, results, ScanSummary.from_results(results)

    def _on_scan_worker_done(self, result: Any, error: Exception | None) -> None:
        if error is not None:
            logger.exception("Scan failed.", exc_info=error)
            self._set_status("✕ SCAN ERROR", _ERROR_COLOR)
            dialogs.show_error(self, "Scan Failed", _friendly_error(error))
            return

        _scan_id, results, summary = result
        completed_display = _format_timestamp(datetime.now(timezone.utc).isoformat())
        self.last_scan_label.configure(text=f"Last scan: {completed_display}")
        self.results_view.set_results(results, timestamp=completed_display)

        if summary.errors:
            self._set_status("⚠ Scan Completed With Errors", _WARNING_COLOR)
            dialogs.show_warning(
                self,
                "Scan Completed With Errors",
                f"{summary.errors} file(s) could not be read during the scan and are "
                "marked ERROR in the results.\n\nThe scan continued with the remaining "
                "files. See the application log for details.",
            )
        elif summary.modified or summary.new or summary.deleted:
            self._set_status("⚠ CHANGES DETECTED", _WARNING_COLOR)
        else:
            self._set_status("✓ NO CHANGES DETECTED", _SUCCESS_COLOR)

    # -- Background worker plumbing -------------------------------------------

    def _run_worker(
        self,
        target: Callable[[ProgressCallback], Any],
        busy_text: str,
        on_done: Callable[[Any, Exception | None], None],
    ) -> None:
        """Run ``target`` on a background thread so the GUI stays responsive
        (section 13), polling its progress/result via a queue.

        ``target`` receives a single ``progress_callback(processed, path)``
        argument and returns a result value, or raises on failure.
        """
        self._set_status(busy_text, _NEUTRAL_COLOR)
        self._set_controls_enabled(False)
        self.progress_frame.grid()
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start()
        self.progress_count_label.configure(text="Files processed: 0")
        self.progress_file_label.configure(text="")

        result_queue: queue.Queue = queue.Queue()

        def progress_callback(processed: int, current_path: str) -> None:
            result_queue.put(("progress", processed, current_path))

        def run() -> None:
            try:
                value = target(progress_callback)
            except Exception as error:  # noqa: BLE001 -- reported to the GUI, never swallowed.
                result_queue.put(("error", error, None))
            else:
                result_queue.put(("done", value, None))

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        self.after(_POLL_INTERVAL_MS, self._poll_worker, result_queue, on_done)

    def _poll_worker(
        self, result_queue: "queue.Queue[tuple[str, Any, Any]]", on_done: Callable[[Any, Exception | None], None]
    ) -> None:
        try:
            while True:
                kind, payload, extra = result_queue.get_nowait()
                if kind == "progress":
                    self.progress_count_label.configure(text=f"Files processed: {payload}")
                    self.progress_file_label.configure(text=f"Current file: {extra}")
                elif kind == "done":
                    self._finish_worker()
                    on_done(payload, None)
                    return
                elif kind == "error":
                    self._finish_worker()
                    on_done(None, payload)
                    return
        except queue.Empty:
            pass
        self.after(_POLL_INTERVAL_MS, self._poll_worker, result_queue, on_done)

    def _finish_worker(self) -> None:
        self.progress_bar.stop()
        self.progress_frame.grid_remove()
        self._set_controls_enabled(True)
