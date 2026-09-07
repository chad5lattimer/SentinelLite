"""SQLite schema and connection management for SentinelLite.

Per PROJECT_SPEC.md section 14 (Storage): SQLite is used for baselines and
scan history, stored locally with no external database server. This module
owns the schema and connection setup only -- reading/writing domain
objects (``Baseline``, scan results) is ``storage.repository``'s job, per
the layered architecture in section 5 (storage must not contain
GUI/business logic, and callers should not write raw SQL against these
tables directly).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

#: Schema for all tables described in PROJECT_SPEC.md section 14.
#: ``scans``/``scan_results`` are created now (Run 3) so the schema is
#: defined in one place; they are only populated starting with the scan
#: engine (Run 4).
_SCHEMA = """
CREATE TABLE IF NOT EXISTS baselines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    root_directory TEXT NOT NULL,
    application_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS baseline_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    baseline_id INTEGER NOT NULL REFERENCES baselines(id) ON DELETE CASCADE,
    relative_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size INTEGER NOT NULL,
    modified_time REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_baseline_files_baseline_id
    ON baseline_files (baseline_id);

CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    baseline_id INTEGER NOT NULL REFERENCES baselines(id) ON DELETE CASCADE,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    modified_count INTEGER NOT NULL DEFAULT 0,
    new_count INTEGER NOT NULL DEFAULT 0,
    deleted_count INTEGER NOT NULL DEFAULT 0,
    unchanged_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS scan_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    relative_path TEXT NOT NULL,
    status TEXT NOT NULL,
    baseline_hash TEXT,
    current_hash TEXT,
    size INTEGER,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_scan_results_scan_id
    ON scan_results (scan_id);
"""


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection to ``db_path``, creating the schema if needed.

    The parent directory is created if it does not exist (mirrors
    ``config.AppPaths.ensure_directories``, but is done defensively here
    too since a repository may be pointed at an arbitrary path, e.g. in
    tests). Foreign keys are enabled explicitly -- SQLite does not enforce
    them by default.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    initialize_schema(connection)
    return connection


def initialize_schema(connection: sqlite3.Connection) -> None:
    """Create any missing tables/indexes. Safe to call on every connection."""
    connection.executescript(_SCHEMA)
    connection.commit()
