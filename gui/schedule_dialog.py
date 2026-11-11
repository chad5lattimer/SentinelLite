""""Scheduled Scans" panel (PROJECT_SPEC.md section 20).

A small modal window matching the spec's layout::

    Scheduled Scans
    [ ] Enable scheduled scanning
    Frequency: [ Daily v ]
    Time:      [ 02:00 AM ]
    [ Save Schedule ]

Presentation only: validation, persistence and Windows Task Scheduler
calls all live in ``core.scheduler`` (``apply_schedule``). A scheduling
failure is reported in a dialog and never affects the core scan path.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

import customtkinter as ctk

from core import scheduler
from core.scheduler import ScheduleConfig, SchedulerError, ScheduleSettings
from gui import dialogs

logger = logging.getLogger(__name__)


class ScheduleDialog(ctk.CTkToplevel):
    """Modal editor for the scheduled-scan settings."""

    def __init__(
        self,
        parent,
        settings_path: Path,
        apply: Callable[[ScheduleSettings, Path], None] = scheduler.apply_schedule,
    ) -> None:
        super().__init__(parent)
        self.title("Scheduled Scans")
        self.resizable(False, False)
        self._settings_path = Path(settings_path)
        self._apply = apply

        current = scheduler.load_schedule_settings(self._settings_path)

        self.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            self, text="Scheduled Scans", font=ctk.CTkFont(size=15, weight="bold")
        ).grid(row=0, column=0, columnspan=2, padx=16, pady=(14, 8), sticky="w")

        self.enabled_var = ctk.BooleanVar(value=current.enabled)
        self.enabled_checkbox = ctk.CTkCheckBox(
            self, text="Enable scheduled scanning", variable=self.enabled_var
        )
        self.enabled_checkbox.grid(row=1, column=0, columnspan=2, padx=16, pady=4, sticky="w")

        ctk.CTkLabel(self, text="Frequency:").grid(row=2, column=0, padx=(16, 8), pady=4, sticky="w")
        self.frequency_var = ctk.StringVar(value=current.config.frequency)
        self.frequency_menu = ctk.CTkOptionMenu(
            self, values=list(scheduler.FREQUENCIES), variable=self.frequency_var
        )
        self.frequency_menu.grid(row=2, column=1, padx=(0, 16), pady=4, sticky="ew")

        ctk.CTkLabel(self, text="Time:").grid(row=3, column=0, padx=(16, 8), pady=4, sticky="w")
        self.time_var = ctk.StringVar(value=scheduler.format_display_time(current.config.time))
        self.time_entry = ctk.CTkEntry(self, textvariable=self.time_var)
        self.time_entry.grid(row=3, column=1, padx=(0, 16), pady=4, sticky="ew")

        ctk.CTkLabel(
            self,
            text="Scans every baselined folder and saves a JSON report to the exports folder.",
            text_color=("gray40", "gray70"),
            wraplength=320,
            justify="left",
        ).grid(row=4, column=0, columnspan=2, padx=16, pady=(4, 8), sticky="w")

        self.save_button = ctk.CTkButton(self, text="Save Schedule", command=self._on_save)
        self.save_button.grid(row=5, column=0, columnspan=2, padx=16, pady=(4, 14), sticky="e")

        self.transient(parent)

    def current_settings(self) -> ScheduleSettings:
        """Build settings from the widgets. Raises ``ValueError`` on bad input."""
        time_24h = scheduler.parse_display_time(self.time_var.get())
        return ScheduleSettings(
            enabled=bool(self.enabled_var.get()),
            config=ScheduleConfig(self.frequency_var.get(), time_24h),
        )

    def _on_save(self) -> bool:
        try:
            settings = self.current_settings()
        except ValueError as error:
            dialogs.show_error(self, "Invalid Schedule", str(error))
            return False
        try:
            self._apply(settings, self._settings_path)
        except SchedulerError as error:
            logger.warning("Saving the scan schedule failed: %s", error)
            dialogs.show_error(
                self,
                "Schedule Not Saved",
                f"The scan schedule could not be saved.\n\n{error}",
            )
            return False
        if settings.enabled:
            message = (
                f"Scheduled scan saved: {settings.config.frequency} at "
                f"{scheduler.format_display_time(settings.config.time)}."
            )
        else:
            message = "Scheduled scanning is disabled."
        dialogs.show_info(self, "Schedule Saved", message)
        self.destroy()
        return True
