"""SQLite connection and schema management for SentinelLite.

Per PROJECT_SPEC.md section 14 (Storage): SQLite is used for local,
offline persistence of baselines and (in a later run) scan history. This
module owns only the connection and schema -- it has no baseline/scan
business logic (that lives in ``core`` and ``storage.repository``).

Tables (PROJECT_SPEC.md section 14):
    - ``baselines``: one row per created baseline.
    - ``baseline_files``: the files captured by a baseline.
    - ``scans``: one row per completed scan (Run 4).
    - ``scan_results``: per-file scan outcomes (Run 4).

The ``scans``/``scan_results`` tables are created now, alongside
``baselines``/``baseline_files``, so the schema is defined in one place per
the spec's table list -- but no repository/query logic for them is added
until Run 4 (Comparison and Scan Engine), per the scope-control rule.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)


class DatabaseCorruptedError(Exception):
    """Raised when the SQLite database file exists but cannot be read.

    This covers a malformed/corrupted database file (e.g. truncated or
    overwritten with non-database bytes) -- PROJECT_SPEC.md section 19
    requires that a corrupted baseline be handled rather than crashing the
    application.
    """


_SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS baselines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        root_directory TEXT NOT NULL,
        application_version TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS baseline_files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        baseline_id INTEGER NOT NULL REFERENCES baselines(id) ON DELETE CASCADE,
        relative_path TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        size INTEGER NOT NULL,
        modified_time REAL NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_baseline_files_baseline_id ON baseline_files(baseline_id)",
    """
    CREATE TABLE IF NOT EXISTS scans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        baseline_id INTEGER NOT NULL REFERENCES baselines(id),
        started_at TEXT NOT NULL,
        completed_at TEXT,
        modified_count INTEGER NOT NULL DEFAULT 0,
        new_count INTEGER NOT NULL DEFAULT 0,
        deleted_count INTEGER NOT NULL DEFAULT 0,
        unchanged_count INTEGER NOT NULL DEFAULT 0,
        error_count INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scan_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
        relative_path TEXT NOT NULL,
        status TEXT NOT NULL,
        baseline_hash TEXT,
        current_hash TEXT,
        size INTEGER,
        error_message TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_scan_results_scan_id ON scan_results(scan_id)",
)


def initialize_database(connection: sqlite3.Connection) -> None:
    """Create the SentinelLite schema if it does not already exist.

    Raises:
        DatabaseCorruptedError: If ``connection`` points at a file that is
            not a valid SQLite database (e.g. corrupted/truncated).
    """
    try:
        with connection:
            connection.execute("PRAGMA foreign_keys = ON")
            for statement in _SCHEMA_STATEMENTS:
                connection.execute(statement)
    except sqlite3.DatabaseError as error:
        # sqlite3 raises DatabaseError (e.g. "file is not a database") for
        # a corrupted/malformed file, not for a missing one -- a missing
        # file is simply created fresh by sqlite3.connect().
        logger.error("Database file is corrupted or unreadable: %s", error)
        raise DatabaseCorruptedError(str(error)) from error


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Open (creating if necessary) the SentinelLite SQLite database.

    Args:
        db_path: Path to the ``.db`` file. Its parent directory must
            already exist (see ``config.AppPaths.ensure_directories``).

    Returns:
        A connection with ``row_factory`` set to ``sqlite3.Row`` and the
        schema already initialized.

    Raises:
        DatabaseCorruptedError: If the file exists but is not a valid
            SQLite database.
    """
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        initialize_database(connection)
    except DatabaseCorruptedError:
        connection.close()
        raise
    return connection


@contextmanager
def connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Context manager that opens a connection and guarantees it is closed.

    Example:
        with connect(config.PATHS.database_path) as conn:
            ...
    """
    connection = get_connection(db_path)
    try:
        yield connection
    finally:
        connection.close()
