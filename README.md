# SentinelLite

A lightweight Windows desktop file integrity monitor (FIM). SentinelLite
creates a cryptographic (SHA-256) baseline of a chosen directory, then
compares the current filesystem state against that baseline to detect
new, modified, deleted, and unchanged files.

See [`PROJECT_SPEC.md`](PROJECT_SPEC.md) for the full technical
specification and development plan.

> **Status:** All 7 planned runs (Foundation through QA & Packaging)
> complete -- SentinelLite meets its MVP scope (`PROJECT_SPEC.md` section
> 2.1). The core engine can recursively enumerate a directory, compute
> SHA-256 hashes, create/save/load a baseline, run a scan that classifies
> every file as NEW/MODIFIED/DELETED/UNCHANGED/ERROR, and persist scan
> history in a local SQLite database. The CustomTkinter GUI is wired to
> all of this: pick a folder, create a baseline (with a confirmation
> before replacing an existing one), run a scan on a background thread so
> the UI never freezes, view a filterable results table with summary
> counts, and export the results of the last scan to CSV or JSON. An
> uncaught GUI-callback exception now surfaces a friendly "Fatal
> application error" dialog instead of vanishing silently (important once
> packaged with `--windowed`, which has no console). `build_exe.bat`
> packages the app with PyInstaller; the section 33 Final Acceptance Test
> passes end-to-end through the real GUI, exports included. Optional
> Windows scheduled scanning was deferred (see
> `status/status_2026-09-10.md`). See [`status/`](status/) for per-run
> progress notes.

## Requirements

- Windows 10/11 (primary target platform)
- Python 3.12+
- Git

## Development Setup

```bat
REM Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate

REM Install dependencies
pip install -r requirements.txt

REM Run the application
python app.py

REM Run the test suite
pytest
```

On macOS/Linux (for development only -- the packaged deliverable targets
Windows), the equivalent commands are:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
pytest
```

## Application Data

SentinelLite stores its database, logs, and exports in a per-user,
writable location rather than inside the install directory:

- Windows: `%LOCALAPPDATA%\SentinelLite\`
- macOS: `~/Library/Application Support/SentinelLite/`
- Linux: `$XDG_DATA_HOME/SentinelLite/` (defaults to `~/.local/share/SentinelLite/`)

This can be overridden for development or testing with the
`SENTINELLITE_DATA_DIR` environment variable.

## Project Structure

```
sentinellite/
├── app.py              # Application entry point
├── config.py           # Metadata, paths, logging configuration
├── core/                # Hashing, filesystem, baseline, scan engine (security logic)
├── storage/              # SQLite database + repository layer
├── gui/                 # CustomTkinter GUI (presentation only): main_window,
│                          results_view (table + filters), dialogs (folder
│                          picker, confirmations, error/info boxes)
├── reports/              # CSV/JSON export (reports/exporter.py)
├── tests/               # pytest test suite
├── status/               # Per-run development status reports
├── assets/, data/, logs/ # Static assets and local runtime data
├── requirements.txt
├── README.md
└── PROJECT_SPEC.md
```

The GUI must never contain hashing or filesystem comparison logic --
that lives in `core/`, per the layered architecture in
`PROJECT_SPEC.md` section 5.

## Packaging

Build a standalone Windows executable with PyInstaller (`PROJECT_SPEC.md`
section 21):

```bat
REM From the project root, with the project's virtual environment active.
build_exe.bat
```

This runs:

```bat
pyinstaller --noconfirm --windowed --name SentinelLite app.py
```

and produces:

```
dist\SentinelLite\SentinelLite.exe
```

Launch `dist\SentinelLite\SentinelLite.exe` directly to verify the
packaged build before distributing it -- it must be able to complete the
full workflow (select folder, create baseline, scan, view results, export
CSV/JSON) exactly like running `python app.py`. The one-folder output is
used rather than `--onefile` because reliability is preferred over a
single executable (section 21); `--onefile` can be added to the
`pyinstaller` command in `build_exe.bat` if a single-file build is
specifically needed, at the cost of slower startup and a higher chance of
antivirus/SmartScreen false positives on an unsigned single-file `.exe`.

The packaging step itself has been structurally verified in this
repository's Linux development environment (a full PyInstaller build of
`app.py` succeeds and the frozen executable launches, creates its
database/log, and runs without error) -- see
`status/status_2026-09-11.md`. Since the primary target platform is
Windows (section 4.1), a Windows machine should still run `build_exe.bat`
and smoke-test the resulting `.exe` before distributing it.

## Security Notes

- SHA-256 is used exclusively for integrity comparisons (no MD5/SHA-1).
- The application is detection-only: it never automatically deletes,
  quarantines, modifies, or restores files.
- The application requires no network connectivity and performs no
  telemetry.
- The baseline is the trust reference: if an attacker can modify both the
  monitored files and the baseline database, file integrity monitoring can
  be defeated. Protect access to the application data directory.

## License

Not yet specified.
