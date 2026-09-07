"""SQLite database layer for SentinelLite.

Per PROJECT_SPEC.md section 14 (Storage):
    - SQLite is preferred for scan history and the baseline reference.
    - The database is a single local file (``sentinellite.db`` by default,
      see ``config.PATHS.database_path``); no external database server is
      required.

This module owns the schema (table creation) and connection handling. It
has no knowledge of ``FileRecord``/``Baseline`` objects -- that mapping
lives in ``storage.repository``, which keeps this module a thin, testable
layer around ``sqlite3``.

Tables (PROJECT_SPEC.md section 14):
    baselines       -- one row per created baseline.
    baseline_files  -- one row per file captured in a baseline.
    scans           -- one row per executed scan (Run 4).
    scan_results    -- one row per per-file comparison result (Run 4).

The ``scans``/``scan_results`` tables are created now, alongside
``baselines``/``baseline_files``, so the schema is defined in one place and
Run 4 does not need a migration step -- but this run (Run 3) does not read
or write them.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from config import PATHS

logger = logging.getLogger(__name__)

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
    ON baseline_files(baseline_id);

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
    ON scan_results(scan_id);
"""


def get_connection(database_path: Path | None = None) -> sqlite3.Connection:
    """Open a SQLite connection to the SentinelLite database, creating the
    schema if it does not already exist.

    Args:
        database_path: Path to the ``.db`` file. Defaults to
            ``config.PATHS.database_path``. The parent directory is created
            if necessary (mirrors ``config.AppPaths.ensure_directories``).

    Returns:
        An open ``sqlite3.Connection`` with foreign keys enabled and row
        access by column name (``sqlite3.Row``).
    """
    path = database_path if database_path is not None else PATHS.database_path
    path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    initialize_schema(connection)
    return connection


def initialize_schema(connection: sqlite3.Connection) -> None:
    """Create all SentinelLite tables/indexes if they do not already exist.

    Safe to call repeatedly against the same connection/database.
    """
    try:
        connection.executescript(_SCHEMA)
        connection.commit()
    except sqlite3.DatabaseError as error:
        # A corrupted or non-SQLite file at database_path surfaces here.
        # Logged and re-raised so callers (storage.repository) can decide
        # how to present this to the user (PROJECT_SPEC.md section 18).
        logger.error("Failed to initialize database schema: %s", error)
        raise
