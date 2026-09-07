"""Baseline creation, loading, and validation for SentinelLite.

This is the core business-logic layer for baselines: it turns a monitored
directory into a ``Baseline`` (via ``core.filesystem`` for enumeration and
hashing) and persists/retrieves it via ``storage.repository`` and
``storage.database``. It has no GUI dependency (PROJECT_SPEC.md section 5)
and no SQL of its own -- that lives entirely in the storage package.

Per PROJECT_SPEC.md section 9 (Baseline Creation) and section 17.2
(Baseline Protection): creating a baseline replaces the *monitoring
reference* used by future scans. Deciding whether to warn the user before
doing so is a GUI-layer concern (Run 5); this module exposes
``has_existing_baseline()`` so that check can be made first.
"""

from __future__ import annotations

import datetime
import logging
import sqlite3
from pathlib import Path

from config import APP_VERSION
from core.filesystem import ProgressCallback, scan_directory
from core.models import Baseline, FileError
from storage import database, repository
from storage.repository import BaselineNotFoundError

logger = logging.getLogger(__name__)

__all__ = [
    "BaselineError",
    "BaselineLoadError",
    "create_baseline",
    "has_existing_baseline",
    "load_baseline",
    "load_latest_baseline",
    "open_database",
]


class BaselineError(Exception):
    """Base class for baseline failures meant to be shown to the user as a
    friendly message rather than a raw traceback (PROJECT_SPEC.md
    section 18)."""


class BaselineLoadError(BaselineError):
    """Raised when a baseline cannot be read -- e.g. the requested id does
    not exist, or the underlying database file is corrupted
    (PROJECT_SPEC.md section 19: "missing baseline is handled" /
    "corrupted baseline is handled")."""


def open_database(database_path: Path) -> sqlite3.Connection:
    """Open (and, if needed, initialize) the SentinelLite database.

    Thin wrapper around ``storage.database.connect`` that turns a
    corrupted/unreadable database file into a friendly ``BaselineLoadError``
    instead of letting a raw ``sqlite3.DatabaseError`` reach the GUI.
    """
    try:
        return database.connect(database_path)
    except sqlite3.DatabaseError as error:
        logger.error("Could not open database at %s: %s", database_path, error)
        raise BaselineLoadError(
            "The saved data could not be read. The database file may be corrupted."
        ) from error


def create_baseline(
    root: Path,
    connection: sqlite3.Connection,
    progress_callback: ProgressCallback | None = None,
) -> tuple[Baseline, list[FileError]]:
    """Create a new baseline for ``root`` and persist it.

    Enumerates and hashes every readable file under ``root``
    (``core.filesystem.scan_directory``), then saves the result as a new
    baseline row via ``storage.repository``. Files that could not be read
    are excluded from the baseline itself and returned separately as
    errors, so the caller can inform the user (section 7.3) without
    failing baseline creation outright.

    This function does not check whether a baseline already exists for
    ``root`` -- see ``has_existing_baseline()``. Warning the user before
    replacing the monitoring reference is a GUI-layer concern (section 9).

    Returns:
        A tuple ``(baseline, errors)``. ``baseline`` is the persisted
        baseline, reloaded from storage so ``baseline_id`` is populated.
    """
    root = Path(root)
    records, errors = scan_directory(root, progress_callback=progress_callback)

    new_baseline = Baseline(
        baseline_id=None,
        created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        root_directory=str(root),
        application_version=APP_VERSION,
        files=tuple(records),
    )

    baseline_id = repository.save_baseline(connection, new_baseline)
    saved_baseline = repository.load_baseline(connection, baseline_id)

    logger.info(
        "Baseline created: id=%s directory=%s files=%d errors=%d",
        baseline_id,
        root,
        len(records),
        len(errors),
    )
    if errors:
        logger.warning(
            "%d file(s) could not be read while creating the baseline.", len(errors)
        )

    return saved_baseline, errors


def has_existing_baseline(connection: sqlite3.Connection) -> bool:
    """Return ``True`` if a baseline has already been saved.

    Intended for the GUI to decide whether to warn the user before
    "Create Baseline" replaces the current monitoring reference
    (section 9).
    """
    return repository.has_any_baseline(connection)


def load_latest_baseline(connection: sqlite3.Connection) -> Baseline | None:
    """Load the most recently created baseline, or ``None`` if none exists.

    Raises:
        BaselineLoadError: If a baseline row exists but cannot be read
            (e.g. unexpected database corruption discovered mid-query).
    """
    try:
        return repository.load_latest_baseline(connection)
    except sqlite3.DatabaseError as error:
        raise BaselineLoadError(
            "The saved baseline could not be read. It may be corrupted."
        ) from error


def load_baseline(connection: sqlite3.Connection, baseline_id: int) -> Baseline:
    """Load a specific baseline by id.

    Raises:
        BaselineLoadError: If ``baseline_id`` does not exist, or the
            baseline exists but cannot be read.
    """
    try:
        return repository.load_baseline(connection, baseline_id)
    except BaselineNotFoundError as error:
        raise BaselineLoadError(f"Baseline {baseline_id} does not exist.") from error
    except sqlite3.DatabaseError as error:
        raise BaselineLoadError(
            "The saved baseline could not be read. It may be corrupted."
        ) from error
