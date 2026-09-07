"""SQLite database layer for SentinelLite.

Per PROJECT_SPEC.md section 14 (Storage). This module owns the raw
``sqlite3`` connection and schema; it contains no baseline/scan business
logic (see ``storage.repository`` for that), and no GUI or `core` imports,
per the layered architecture in PROJECT_SPEC.md section 5 (Storage is the
lowest layer).

Only the ``baselines`` and ``baseline_files`` tables are created in this
run (PROJECT_SPEC.md section 28, Run 3 -- Baseline System). The ``scans``
and ``scan_results`` tables are deferred to Run 4 (Comparison and Scan
Engine) per the scope-control rule (section 38); they will be added to
``_SCHEMA_STATEMENTS`` when that run implements ``core/scanner.py``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

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
)


def connect(database_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection to ``database_path``, creating the schema if needed.

    The parent directory is created if it does not already exist. Rows are
    returned as ``sqlite3.Row`` for convenient access by column name, and
    foreign keys are enforced.

    Raises:
        sqlite3.DatabaseError: If ``database_path`` exists but is not a
            valid SQLite database (e.g. a corrupted or truncated file).
            Callers that need a user-friendly "corrupted baseline" message
            (PROJECT_SPEC.md section 19) should catch this -- see
            ``storage.repository.BaselineRepository``.
    """
    database_path = Path(database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    _initialize_schema(connection)
    return connection


def _initialize_schema(connection: sqlite3.Connection) -> None:
    with connection:
        for statement in _SCHEMA_STATEMENTS:
            connection.execute(statement)
