"""Baseline data-access layer for SentinelLite.

Per PROJECT_SPEC.md section 28 (Run 3): plain SQL read/write functions over
the ``baselines`` and ``baseline_files`` tables (see ``storage.database``
for the schema). This module has no hashing/filesystem logic and no GUI
dependency -- it only translates between ``core.models.FileRecord`` /
baseline metadata and SQLite rows.

Scan-history persistence (``scans`` / ``scan_results``) is deferred to
Run 4 (Comparison and Scan Engine), per the scope-control rule.
"""

from __future__ import annotations

import sqlite3
from typing import Iterable, NamedTuple

from core.models import FileRecord


class BaselineMetadata(NamedTuple):
    """Metadata for a stored baseline, without its (potentially large) file list."""

    baseline_id: int
    created_at: str
    root_directory: str
    application_version: str


def insert_baseline(
    connection: sqlite3.Connection,
    *,
    created_at: str,
    root_directory: str,
    application_version: str,
    files: Iterable[FileRecord],
) -> int:
    """Persist a new baseline and its files, replacing no prior baseline.

    Every call inserts a brand-new ``baselines`` row (baselines are never
    overwritten in place), so scan history and prior baselines are
    preserved. Deciding *whether* to create a new baseline -- and warning
    the user that it replaces the active monitoring reference -- is a GUI
    concern (PROJECT_SPEC.md section 9), not this repository's.

    Returns:
        The new baseline's ``id``.
    """
    with connection:
        cursor = connection.execute(
            "INSERT INTO baselines (created_at, root_directory, application_version) "
            "VALUES (?, ?, ?)",
            (created_at, root_directory, application_version),
        )
        baseline_id = cursor.lastrowid

        connection.executemany(
            "INSERT INTO baseline_files "
            "(baseline_id, relative_path, sha256, size, modified_time) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                (baseline_id, record.path, record.sha256, record.size, record.modified_time)
                for record in files
            ),
        )

    return baseline_id


def get_latest_baseline_id(connection: sqlite3.Connection) -> int | None:
    """Return the id of the most recently created baseline, or None if none exist."""
    row = connection.execute(
        "SELECT id FROM baselines ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return row["id"] if row is not None else None


def get_baseline_metadata(
    connection: sqlite3.Connection, baseline_id: int
) -> BaselineMetadata | None:
    """Return a baseline's metadata (without files), or None if it does not exist."""
    row = connection.execute(
        "SELECT id, created_at, root_directory, application_version "
        "FROM baselines WHERE id = ?",
        (baseline_id,),
    ).fetchone()
    if row is None:
        return None
    return BaselineMetadata(
        baseline_id=row["id"],
        created_at=row["created_at"],
        root_directory=row["root_directory"],
        application_version=row["application_version"],
    )


def get_baseline_files(connection: sqlite3.Connection, baseline_id: int) -> list[FileRecord]:
    """Return every file captured by a baseline, in insertion order."""
    rows = connection.execute(
        "SELECT relative_path, sha256, size, modified_time "
        "FROM baseline_files WHERE baseline_id = ? ORDER BY id",
        (baseline_id,),
    ).fetchall()
    return [
        FileRecord(
            path=row["relative_path"],
            sha256=row["sha256"],
            size=row["size"],
            modified_time=row["modified_time"],
        )
        for row in rows
    ]
