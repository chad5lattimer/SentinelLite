"""Baseline persistence for SentinelLite.

Per PROJECT_SPEC.md section 14 (Storage) and section 28 (Run 3
acceptance criteria): save a ``Baseline`` to SQLite, load it back
unchanged, and handle a missing or corrupted baseline gracefully rather
than crashing the application.

This module contains no hashing or filesystem logic (that stays in
``core``) and no GUI logic (per the layered architecture in section 5).
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import replace
from pathlib import Path

from config import PATHS
from core.baseline import BaselineError, validate_baseline
from core.models import Baseline, FileRecord
from storage.database import get_connection

logger = logging.getLogger(__name__)


class BaselineRepository:
    """Reads and writes ``Baseline`` objects to a local SQLite database."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path is not None else PATHS.database_path

    def save_baseline(self, baseline: Baseline) -> Baseline:
        """Persist ``baseline`` and return a copy with ``baseline_id`` set.

        The baseline row and all of its file rows are written in a single
        transaction, so a save either fully succeeds or leaves no partial
        baseline behind.

        Raises:
            BaselineError: If the baseline is malformed, or the write
                fails (e.g. a read-only or corrupted database file).
        """
        validate_baseline(baseline)

        try:
            connection = get_connection(self._db_path)
            try:
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
                        [
                            (baseline_id, file.path, file.sha256, file.size, file.modified_time)
                            for file in baseline.files
                        ],
                    )
            finally:
                connection.close()
        except sqlite3.DatabaseError as error:
            logger.exception("Failed to save baseline to %s.", self._db_path)
            raise BaselineError(
                f"Could not save the baseline to {self._db_path}. "
                "The database file may be corrupted or unwritable."
            ) from error

        logger.info("Saved baseline %s (%d files) to %s.", baseline_id, len(baseline.files), self._db_path)
        return replace(baseline, baseline_id=baseline_id)

    def load_baseline(self, baseline_id: int) -> Baseline | None:
        """Load the baseline with the given id, or ``None`` if it does not exist.

        Raises:
            BaselineError: If the database cannot be read, or the stored
                data is malformed (a corrupted baseline).
        """
        try:
            connection = get_connection(self._db_path)
            try:
                row = connection.execute(
                    "SELECT id, created_at, root_directory, application_version "
                    "FROM baselines WHERE id = ?",
                    (baseline_id,),
                ).fetchone()
                if row is None:
                    return None
                file_rows = connection.execute(
                    "SELECT relative_path, sha256, size, modified_time "
                    "FROM baseline_files WHERE baseline_id = ? ORDER BY relative_path",
                    (baseline_id,),
                ).fetchall()
            finally:
                connection.close()
        except sqlite3.DatabaseError as error:
            logger.exception("Failed to read baseline %s from %s.", baseline_id, self._db_path)
            raise BaselineError(
                f"Could not read the baseline database at {self._db_path}. "
                "The file may be corrupted."
            ) from error

        return self._row_to_baseline(row, file_rows)

    def load_latest_baseline(self) -> Baseline | None:
        """Load the most recently created baseline, or ``None`` if none exists.

        Raises:
            BaselineError: If the database cannot be read or is corrupted.
        """
        try:
            connection = get_connection(self._db_path)
            try:
                row = connection.execute(
                    "SELECT id, created_at, root_directory, application_version "
                    "FROM baselines ORDER BY id DESC LIMIT 1"
                ).fetchone()
                if row is None:
                    return None
                file_rows = connection.execute(
                    "SELECT relative_path, sha256, size, modified_time "
                    "FROM baseline_files WHERE baseline_id = ? ORDER BY relative_path",
                    (row["id"],),
                ).fetchall()
            finally:
                connection.close()
        except sqlite3.DatabaseError as error:
            logger.exception("Failed to read latest baseline from %s.", self._db_path)
            raise BaselineError(
                f"Could not read the baseline database at {self._db_path}. "
                "The file may be corrupted."
            ) from error

        return self._row_to_baseline(row, file_rows)

    def has_baseline(self) -> bool:
        """Return whether at least one baseline has been saved.

        Intended for the GUI layer (Run 5) to decide whether to warn the
        user before replacing an existing baseline (PROJECT_SPEC.md
        section 9 / 11.2).
        """
        return self.load_latest_baseline() is not None

    @staticmethod
    def _row_to_baseline(row: sqlite3.Row, file_rows: list[sqlite3.Row]) -> Baseline:
        try:
            files = tuple(
                FileRecord(
                    path=file_row["relative_path"],
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
        except (KeyError, IndexError, TypeError) as error:
            raise BaselineError("The stored baseline is missing required data.") from error

        validate_baseline(baseline)
        return baseline
