# SentinelLite

A lightweight Windows desktop file integrity monitor (FIM). SentinelLite
creates a cryptographic (SHA-256) baseline of a chosen directory, then
compares the current filesystem state against that baseline to detect
new, modified, deleted, and unchanged files.

See [`PROJECT_SPEC.md`](PROJECT_SPEC.md) for the full technical
specification and development plan.

> **Status:** All seven scheduled runs are complete (Foundation through QA
> and Packaging). The core engine recursively enumerates a directory,
> computes SHA-256 hashes, creates/saves/loads a baseline, runs a scan
> that classifies every file as NEW/MODIFIED/DELETED/UNCHANGED/ERROR, and
> persists scan history in a local SQLite database. The CustomTkinter GUI
> is wired to all of this: pick a folder, create a baseline (with a
> confirmation before replacing an existing one), run a scan on a
> background thread so the UI never freezes, view a filterable results
> table with summary counts, and export the results of the last scan to
> CSV or JSON. Optional Windows scheduled scanning was deferred (see
> `status/status_2026-09-10.md`). `PROJECT_SPEC.md` section 33's Final
> Acceptance Test passes end-to-end, and `build_exe.bat` packages the
> application with PyInstaller (verified with a Linux smoke build in this
> development environment; an actual Windows `.exe` build is otherwise
> unverified, since no Windows host is available here -- see
> `status/status_2026-09-10-run7.md`). See [`status/`](status/) for
> per-run progress notes.

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
REM From a Windows checkout, inside the project's virtual environment:
build_exe.bat
```

This runs:

```bat
pyinstaller --noconfirm --windowed --name SentinelLite --add-data "assets;assets" app.py
```

and produces `dist\SentinelLite\SentinelLite.exe`. Application data
(database, logs, exports) is written to `%LOCALAPPDATA%\SentinelLite\`,
never into the install directory (section 22), so the `dist\SentinelLite`
folder can be copied or reinstalled without losing or leaking prior scan
data.

`build_exe.bat` has been smoke-tested on Linux (the packaging pipeline
resolves all imports, PyInstaller's CustomTkinter/Tk hooks run cleanly,
and the resulting binary launches and creates its app-data directory
correctly) but has not been run on an actual Windows machine, since this
development environment has none available. Building and launching the
real `SentinelLite.exe` on Windows 10/11 is the one remaining
verification step before the packaged deliverable itself is confirmed.

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
