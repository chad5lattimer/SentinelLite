# SentinelLite

A lightweight Windows desktop file integrity monitor (FIM). SentinelLite
creates a cryptographic (SHA-256) baseline of a chosen directory, then
compares the current filesystem state against that baseline to detect
new, modified, deleted, and unchanged files.

See [`PROJECT_SPEC.md`](PROJECT_SPEC.md) for the full technical
specification and development plan.

> **Status:** Run 1 (Foundation), Run 2 (Hashing and Filesystem Engine),
> Run 3 (Baseline System), and Run 4 (Comparison and Scan Engine) complete.
> The core engine can recursively enumerate a directory, compute SHA-256
> hashes, create/save/load a baseline, run a scan that classifies every
> file as NEW/MODIFIED/DELETED/UNCHANGED/ERROR, and persist scan history
> in a local SQLite database. GUI wiring and reporting land in subsequent
> runs. See [`status/`](status/) for per-run progress notes.

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
├── gui/                 # CustomTkinter GUI (presentation only)
├── reports/              # CSV/JSON export
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

Packaging into `SentinelLite.exe` via PyInstaller is implemented in a
later development run (see `PROJECT_SPEC.md` section 21 and section 32).

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
