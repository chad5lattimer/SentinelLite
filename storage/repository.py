"""Baseline persistence for SentinelLite.

Maps between ``core.baseline.Baseline`` / ``core.models.FileRecord`` objects
and the SQLite ``baselines`` / ``baseline_files`` tables defined in
``storage.database`` (PROJECT_SPEC.md section 14).

This module contains no hashing or filesystem-enumeration logic -- it only
persists and retrieves already-built ``Baseline`` objects, per the layered
architecture in PROJECT_SPEC.md section 5 (GUI -> application logic ->
security/core logic -> storage).
"""

from __future__ import annotations

import logging
import sqlite3
from typing import TYPE_CHECKING

from core.models import FileRecord

if TYPE_CHECKING:
    from core.baseline import Baseline

logger = logging.getLogger(__name__)


class BaselineNotFoundError(Exception):
    """Raised when no baseline exists for the requested directory/id."""


class BaselineCorruptedError(Exception):
    """Raised when a baseline row exists but its data cannot be read back
    into a valid ``Baseline`` (e.g. unreadable database file, missing
    columns from a damaged row). Kept distinct from ``BaselineNotFoundError``
    so callers/GUI can show "no baseline yet" vs. "baseline is damaged"
    (PROJECT_SPEC.md section 19: both must be handled)."""


class BaselineRepository:
    """Reads and writes baselines against a SQLite connection.

    A thin wrapper is used (rather than free functions taking a connection
    each call) so a single open connection can be reused across a session,
    matching how the GUI (Run 5) will hold one repository for the
    application's lifetime.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def save(self, baseline: "Baseline") -> int:
        """Persist ``baseline`` as a new row, replacing any previous
        baseline for the same ``root_directory``.

        Per PROJECT_SPEC.md section 9, creating a baseline replaces the
        prior monitoring reference for that directory -- the GUI is
        responsible for warning the user before calling this (section 9 /
        17.2); this method performs the replacement transactionally so a
        failure partway through does not leave an orphaned or partial
        baseline.

        Returns:
            The database id assigned to the new baseline row.
        """
        try:
            with self._connection:
                self._connection.execute(
                    "DELETE FROM baselines WHERE root_directory = ?",
                    (baseline.root_directory,),
                )
                cursor = self._connection.execute(
                    "INSERT INTO baselines (created_at, root_directory, "
                    "application_version) VALUES (?, ?, ?)",
                    (baseline.created_at, baseline.root_directory, baseline.application_version),
                )
                baseline_id = cursor.lastrowid
                self._connection.executemany(
                    "INSERT INTO baseline_files (baseline_id, relative_path, "
                    "sha256, size, modified_time) VALUES (?, ?, ?, ?, ?)",
                    [
                        (baseline_id, record.path, record.sha256, record.size, record.modified_time)
                        for record in baseline.files
                    ],
                )
        except sqlite3.DatabaseError as error:
            logger.error("Failed to save baseline for %s: %s", baseline.root_directory, error)
            raise

        logger.info(
            "Saved baseline %s for %s (%d files)",
            baseline_id,
            baseline.root_directory,
            len(baseline.files),
        )
        return baseline_id

    def load_latest_for_directory(self, root_directory: str) -> "Baseline":
        """Load the current baseline for ``root_directory``.

        Raises:
            BaselineNotFoundError: If no baseline has been created for this
                directory (PROJECT_SPEC.md section 19: "Missing baseline is
                handled").
            BaselineCorruptedError: If the baseline row exists but its data
                cannot be read back (section 19: "Corrupted baseline is
                handled").
        """
        try:
            row = self._connection.execute(
                "SELECT id, created_at, root_directory, application_version "
                "FROM baselines WHERE root_directory = ?",
                (root_directory,),
            ).fetchone()
        except sqlite3.DatabaseError as error:
            logger.error("Failed to query baseline for %s: %s", root_directory, error)
            raise BaselineCorruptedError(str(error)) from error

        if row is None:
            raise BaselineNotFoundError(f"No baseline exists for directory: {root_directory}")

        return self._load_by_row(row)

    def load_by_id(self, baseline_id: int) -> "Baseline":
        """Load a specific baseline by its database id.

        Raises the same exceptions as ``load_latest_for_directory``.
        """
        try:
            row = self._connection.execute(
                "SELECT id, created_at, root_directory, application_version "
                "FROM baselines WHERE id = ?",
                (baseline_id,),
            ).fetchone()
        except sqlite3.DatabaseError as error:
            logger.error("Failed to query baseline %s: %s", baseline_id, error)
            raise BaselineCorruptedError(str(error)) from error

        if row is None:
            raise BaselineNotFoundError(f"No baseline exists with id: {baseline_id}")

        return self._load_by_row(row)

    def _load_by_row(self, row: sqlite3.Row) -> "Baseline":
        from core.baseline import Baseline  # local import: avoid a circular import at module load

        try:
            file_rows = self._connection.execute(
                "SELECT relative_path, sha256, size, modified_time "
                "FROM baseline_files WHERE baseline_id = ?",
                (row["id"],),
            ).fetchall()
        except sqlite3.DatabaseError as error:
            logger.error("Failed to load files for baseline %s: %s", row["id"], error)
            raise BaselineCorruptedError(str(error)) from error

        try:
            files = [
                FileRecord(
                    path=file_row["relative_path"],
                    sha256=file_row["sha256"],
                    size=file_row["size"],
                    modified_time=file_row["modified_time"],
                )
                for file_row in file_rows
            ]
            return Baseline(
                baseline_id=row["id"],
                created_at=row["created_at"],
                root_directory=row["root_directory"],
                application_version=row["application_version"],
                files=files,
            )
        except (KeyError, IndexError, TypeError) as error:
            # A row with missing/unexpected columns (e.g. a hand-edited or
            # partially-migrated database) surfaces here as "corrupted"
            # rather than a raw KeyError reaching the GUI.
            logger.error("Corrupted baseline row for id %s: %s", row["id"], error)
            raise BaselineCorruptedError(str(error)) from error

    def exists_for_directory(self, root_directory: str) -> bool:
        """Return whether a baseline currently exists for ``root_directory``."""
        row = self._connection.execute(
            "SELECT 1 FROM baselines WHERE root_directory = ?",
            (root_directory,),
        ).fetchone()
        return row is not None
