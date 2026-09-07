"""Baseline persistence for SentinelLite.

Bridges ``core.baseline``'s storage-agnostic ``Baseline``/``BaselineFile``
objects and the SQLite schema defined in ``storage.database``. Per the
layered architecture in PROJECT_SPEC.md section 5, this module is the only
place that issues SQL for baselines; ``core.baseline`` has no knowledge of
SQLite.

Each call to ``save()`` inserts a new baseline row rather than overwriting
the previous one (older baselines are simply not returned by
``load_latest()``). This keeps baseline history recoverable and avoids
destructive writes at the storage layer; the GUI (Run 5) is responsible for
warning the user before replacing the active baseline (PROJECT_SPEC.md
sections 2.1 and 9 -- "Prevent accidental silent replacement").
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.baseline import Baseline, BaselineFile, BaselineValidationError, validate_baseline
from storage.database import connect


class BaselineNotFoundError(Exception):
    """Raised when no baseline exists yet, or a requested id doesn't exist."""


class BaselineRepository:
    """Save and load ``Baseline`` objects against a SQLite database."""

    def __init__(self, database_path: Path):
        self._database_path = Path(database_path)
        self._connection: sqlite3.Connection | None = None

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __enter__(self) -> "BaselineRepository":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _conn(self) -> sqlite3.Connection:
        if self._connection is None:
            try:
                self._connection = connect(self._database_path)
            except sqlite3.DatabaseError as error:
                raise BaselineValidationError(f"Baseline database is corrupted: {error}") from error
        return self._connection

    def save(self, baseline: Baseline) -> Baseline:
        """Persist ``baseline`` as a new row and return it with ``baseline_id`` set."""
        conn = self._conn()
        with conn:
            cursor = conn.execute(
                "INSERT INTO baselines (created_at, root_directory, application_version) "
                "VALUES (?, ?, ?)",
                (baseline.created_at, baseline.root_directory, baseline.application_version),
            )
            baseline_id = cursor.lastrowid
            conn.executemany(
                "INSERT INTO baseline_files "
                "(baseline_id, relative_path, sha256, size, modified_time) VALUES (?, ?, ?, ?, ?)",
                [
                    (baseline_id, entry.relative_path, entry.sha256, entry.size, entry.modified_time)
                    for entry in baseline.files
                ],
            )

        return Baseline(
            baseline_id=baseline_id,
            root_directory=baseline.root_directory,
            created_at=baseline.created_at,
            application_version=baseline.application_version,
            files=baseline.files,
        )

    def has_baseline(self) -> bool:
        """Return True if at least one baseline has been saved."""
        row = self._conn().execute("SELECT 1 FROM baselines LIMIT 1").fetchone()
        return row is not None

    def load_latest(self) -> Baseline:
        """Load the most recently created baseline.

        Raises:
            BaselineNotFoundError: No baseline has been saved yet.
            BaselineValidationError: The stored baseline is malformed or
                the database is corrupted.
        """
        row = self._conn().execute(
            "SELECT id, created_at, root_directory, application_version "
            "FROM baselines ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            raise BaselineNotFoundError("No baseline has been created yet.")
        return self._load_from_row(row)

    def load(self, baseline_id: int) -> Baseline:
        """Load a specific baseline by id.

        Raises:
            BaselineNotFoundError: No baseline with ``baseline_id`` exists.
            BaselineValidationError: The stored baseline is malformed or
                the database is corrupted.
        """
        row = self._conn().execute(
            "SELECT id, created_at, root_directory, application_version "
            "FROM baselines WHERE id = ?",
            (baseline_id,),
        ).fetchone()
        if row is None:
            raise BaselineNotFoundError(f"No baseline with id {baseline_id}.")
        return self._load_from_row(row)

    def _load_from_row(self, row: sqlite3.Row) -> Baseline:
        try:
            file_rows = self._conn().execute(
                "SELECT relative_path, sha256, size, modified_time "
                "FROM baseline_files WHERE baseline_id = ?",
                (row["id"],),
            ).fetchall()
        except sqlite3.DatabaseError as error:
            raise BaselineValidationError(f"Baseline database is corrupted: {error}") from error

        files = tuple(
            BaselineFile(
                relative_path=file_row["relative_path"],
                sha256=file_row["sha256"],
                size=file_row["size"],
                modified_time=file_row["modified_time"],
            )
            for file_row in file_rows
        )
        baseline = Baseline(
            baseline_id=row["id"],
            created_at=row["created_at"],
            root_directory=row["root_directory"],
            application_version=row["application_version"],
            files=files,
        )
        validate_baseline(baseline)
        return baseline
