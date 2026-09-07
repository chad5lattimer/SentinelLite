"""SQLite connection and schema management for SentinelLite.

Per PROJECT_SPEC.md section 14 (Storage), this module owns the local
SQLite database (``sentinellite.db``) and nothing else -- no baseline or
scan business logic lives here (that is storage.repository and
core.baseline / core.scanner). All four recommended tables (baselines,
baseline_files, scans, scan_results) are created up front: Run 3 only
populates the baseline tables, but creating the full schema now avoids a
migration step when the scan engine (Run 4) and reporting (Run 6) land,
and ``CREATE TABLE IF NOT EXISTS`` makes this safe to repeat.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

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


def connect(database_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection to ``database_path``, creating the parent
    directory and schema if they do not already exist.

    Rows are returned as ``sqlite3.Row`` so callers can access columns by
    name, and foreign keys are enabled so ``ON DELETE CASCADE`` applies.

    Raises:
        sqlite3.DatabaseError: If ``database_path`` exists but is not a
            valid SQLite database (e.g. a corrupted or truncated file).
            Callers that need a user-friendly message for this case (see
            PROJECT_SPEC.md section 19, "corrupted baseline is handled")
            should catch this -- see core.baseline.open_database().
    """
    database_path = Path(database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        initialize_schema(connection)
    except sqlite3.DatabaseError:
        connection.close()
        raise
    return connection


def initialize_schema(connection: sqlite3.Connection) -> None:
    """Create all tables/indexes if they do not already exist. Idempotent."""
    connection.executescript(_SCHEMA)
    connection.commit()
