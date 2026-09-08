"""Baseline and scan-history data-access layer for SentinelLite.

Per PROJECT_SPEC.md section 28 (Run 3) and section 29 (Run 4): plain SQL
read/write functions over the ``baselines``, ``baseline_files``, ``scans``,
and ``scan_results`` tables (see ``storage.database`` for the schema). This
module has no hashing/filesystem/comparison logic and no GUI dependency --
it only translates between ``core`` dataclasses and SQLite rows.
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Iterable, NamedTuple

from core.models import FileRecord, ScanStatus

if TYPE_CHECKING:
    # Imported only for type checking to avoid a circular import --
    # core.scanner imports this module.
    from core.scanner import ScanFileResult


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


class ScanMetadata(NamedTuple):
    """Metadata and summary counts for a stored scan, without its (potentially
    large) per-file results."""

    scan_id: int
    baseline_id: int
    started_at: str
    completed_at: str | None
    modified_count: int
    new_count: int
    deleted_count: int
    unchanged_count: int
    error_count: int


class ScanResultRow(NamedTuple):
    """A single persisted per-file scan outcome."""

    path: str
    status: str
    baseline_hash: str | None
    current_hash: str | None
    size: int | None
    error_message: str | None


def insert_scan(
    connection: sqlite3.Connection,
    *,
    baseline_id: int,
    started_at: str,
    completed_at: str,
    modified_count: int,
    new_count: int,
    deleted_count: int,
    unchanged_count: int,
    error_count: int,
    results: Iterable["ScanFileResult"],
) -> int:
    """Persist a completed scan and its per-file results as new rows.

    Every call inserts a brand-new ``scans`` row, so scan history
    accumulates across runs against the same baseline.

    Returns:
        The new scan's ``id``.
    """
    with connection:
        cursor = connection.execute(
            "INSERT INTO scans "
            "(baseline_id, started_at, completed_at, modified_count, new_count, "
            "deleted_count, unchanged_count, error_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                baseline_id,
                started_at,
                completed_at,
                modified_count,
                new_count,
                deleted_count,
                unchanged_count,
                error_count,
            ),
        )
        scan_id = cursor.lastrowid

        connection.executemany(
            "INSERT INTO scan_results "
            "(scan_id, relative_path, status, baseline_hash, current_hash, size, error_message) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                (
                    scan_id,
                    result.path,
                    result.status.value if isinstance(result.status, ScanStatus) else result.status,
                    result.baseline_hash,
                    result.current_hash,
                    result.size,
                    result.error_message,
                )
                for result in results
            ),
        )

    return scan_id


def get_latest_scan_id(connection: sqlite3.Connection, baseline_id: int | None = None) -> int | None:
    """Return the id of the most recently completed scan, or None if none exist.

    If ``baseline_id`` is given, only scans run against that baseline are
    considered.
    """
    if baseline_id is None:
        row = connection.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1").fetchone()
    else:
        row = connection.execute(
            "SELECT id FROM scans WHERE baseline_id = ? ORDER BY id DESC LIMIT 1",
            (baseline_id,),
        ).fetchone()
    return row["id"] if row is not None else None


def get_scan_metadata(connection: sqlite3.Connection, scan_id: int) -> ScanMetadata | None:
    """Return a scan's metadata and summary counts, or None if it does not exist."""
    row = connection.execute(
        "SELECT id, baseline_id, started_at, completed_at, modified_count, new_count, "
        "deleted_count, unchanged_count, error_count FROM scans WHERE id = ?",
        (scan_id,),
    ).fetchone()
    if row is None:
        return None
    return ScanMetadata(
        scan_id=row["id"],
        baseline_id=row["baseline_id"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        modified_count=row["modified_count"],
        new_count=row["new_count"],
        deleted_count=row["deleted_count"],
        unchanged_count=row["unchanged_count"],
        error_count=row["error_count"],
    )


def get_scan_results(connection: sqlite3.Connection, scan_id: int) -> list[ScanResultRow]:
    """Return every per-file result recorded for a scan, in insertion order."""
    rows = connection.execute(
        "SELECT relative_path, status, baseline_hash, current_hash, size, error_message "
        "FROM scan_results WHERE scan_id = ? ORDER BY id",
        (scan_id,),
    ).fetchall()
    return [
        ScanResultRow(
            path=row["relative_path"],
            status=row["status"],
            baseline_hash=row["baseline_hash"],
            current_hash=row["current_hash"],
            size=row["size"],
            error_message=row["error_message"],
        )
        for row in rows
    ]
