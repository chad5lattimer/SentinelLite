"""Main application window for SentinelLite.

Run 1 scope: a basic, clean CustomTkinter window shell with the header and
placeholder sections described in PROJECT_SPEC.md section 11.2. No
filesystem scanning, hashing, or baseline logic is wired in yet -- that
begins in later runs (see PROJECT_SPEC.md sections 26-31). This module must
stay free of security/core logic; it only builds and displays UI.
"""

from __future__ import annotations

import customtkinter as ctk

from config import APP_DESCRIPTION, APP_NAME


class MainWindow(ctk.CTk):
    """Top-level application window.

    Holds only presentation concerns for now: a header, and placeholder
    sections for the monitored directory, baseline, and scan status that
    will be populated with live data once the core engine (Runs 2-4) and
    GUI integration (Run 5) land.
    """

    def __init__(self) -> None:
        super().__init__()

        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        self.title(f"{APP_NAME} - {APP_DESCRIPTION}")
        self.geometry("760x560")
        self.minsize(640, 480)

        self._build_layout()

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_directory_section()
        self._build_baseline_section()
        self._build_scan_section()
        self._build_status_section()

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
            section, text="Change Folder", state="disabled"
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
            section, text="Create Baseline", state="disabled"
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

        self.scan_now_button = ctk.CTkButton(section, text="Scan Now", state="disabled")
        self.scan_now_button.grid(row=1, column=1, padx=16, pady=(0, 12), sticky="e")

    def _build_status_section(self) -> None:
        section = ctk.CTkFrame(self)
        section.grid(row=4, column=0, padx=20, pady=(0, 20), sticky="ew")
        section.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(
            section,
            text="Select a folder to begin.",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.status_label.grid(row=0, column=0, padx=16, pady=16)
