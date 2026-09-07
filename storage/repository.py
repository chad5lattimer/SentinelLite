"""Baseline persistence for SentinelLite.

Translates between the storage-agnostic ``core.models.Baseline`` /
``core.models.FileRecord`` dataclasses and the SQLite schema defined in
``storage.database``. This is the only module that should contain
baseline SQL -- per the layered architecture in PROJECT_SPEC.md section 5,
``core.baseline`` works with plain dataclasses and delegates all
persistence here.
"""

from __future__ import annotations

import sqlite3

from core.models import Baseline, FileRecord


class BaselineNotFoundError(LookupError):
    """Raised when a requested baseline id does not exist in the database."""


def save_baseline(connection: sqlite3.Connection, baseline: Baseline) -> int:
    """Persist ``baseline`` (and its files) as a new row and return its id.

    Each call inserts a *new* baseline row rather than overwriting an
    existing one, so prior baselines remain in the database as history;
    the "current" baseline is whichever one was created most recently
    (see ``load_latest_baseline``). Whether the user should be warned
    before superseding an existing baseline is a GUI-layer concern
    (PROJECT_SPEC.md section 9) -- see ``core.baseline.has_existing_baseline``.
    """
    with connection:
        cursor = connection.execute(
            "INSERT INTO baselines (created_at, root_directory, application_version) "
            "VALUES (?, ?, ?)",
            (baseline.created_at, baseline.root_directory, baseline.application_version),
        )
        baseline_id = cursor.lastrowid
        connection.executemany(
            "INSERT INTO baseline_files "
            "(baseline_id, relative_path, sha256, size, modified_time) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                (baseline_id, record.path, record.sha256, record.size, record.modified_time)
                for record in baseline.files
            ),
        )
    return baseline_id


def load_baseline(connection: sqlite3.Connection, baseline_id: int) -> Baseline:
    """Load a specific baseline (and all of its files) by id.

    Raises:
        BaselineNotFoundError: If no baseline with ``baseline_id`` exists.
    """
    row = connection.execute(
        "SELECT id, created_at, root_directory, application_version "
        "FROM baselines WHERE id = ?",
        (baseline_id,),
    ).fetchone()
    if row is None:
        raise BaselineNotFoundError(f"No baseline with id {baseline_id}.")
    return _baseline_from_row(connection, row)


def load_latest_baseline(connection: sqlite3.Connection) -> Baseline | None:
    """Load the most recently created baseline, or ``None`` if none exists."""
    row = connection.execute(
        "SELECT id, created_at, root_directory, application_version "
        "FROM baselines ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    return _baseline_from_row(connection, row)


def has_any_baseline(connection: sqlite3.Connection) -> bool:
    """Return ``True`` if at least one baseline has been saved."""
    row = connection.execute("SELECT 1 FROM baselines LIMIT 1").fetchone()
    return row is not None


def _baseline_from_row(connection: sqlite3.Connection, row: sqlite3.Row) -> Baseline:
    file_rows = connection.execute(
        "SELECT relative_path, sha256, size, modified_time "
        "FROM baseline_files WHERE baseline_id = ?",
        (row["id"],),
    ).fetchall()
    files = tuple(
        FileRecord(
            path=file_row["relative_path"],
            sha256=file_row["sha256"],
            size=file_row["size"],
            modified_time=file_row["modified_time"],
        )
        for file_row in file_rows
    )
    return Baseline(
        baseline_id=row["id"],
        created_at=row["created_at"],
        root_directory=row["root_directory"],
        application_version=row["application_version"],
        files=files,
    )
