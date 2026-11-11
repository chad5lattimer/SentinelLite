"""Optional scheduled scanning (PROJECT_SPEC.md section 20).

Per the spec, scheduling uses Windows Task Scheduler (``schtasks.exe``)
rather than a custom daemon. This module provides:

    - ``ScheduleConfig``: a validated frequency/time pair.
    - ``build_create_command`` / ``build_delete_command`` /
      ``build_query_command``: pure functions producing ``schtasks``
      argument lists (fully unit-testable on any platform).
    - ``install_schedule`` / ``remove_schedule`` / ``is_schedule_installed``:
      thin wrappers that execute those commands through an injectable
      ``runner`` (defaults to ``subprocess.run``; refuses to run off
      Windows unless a runner is supplied).
    - ``run_scheduled_scan``: the headless job the scheduled task invokes
      (``SentinelLite.exe --scheduled-scan``). It scans every previously
      baselined folder against its most recent baseline, saves scan
      history, and writes a JSON report per folder to the exports dir.

Nothing here is imported by the GUI's core scan path, so a scheduling
failure cannot compromise the core application (section 20).
"""

from __future__ import annotations

import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

from config import APP_NAME
from core.baseline import find_baseline_for_directory
from core.scanner import ScanSummary, run_scan, save_scan
from reports.exporter import default_export_filename, export_json
from storage import repository
from storage.database import connect

logger = logging.getLogger(__name__)

TASK_NAME: str = f"{APP_NAME} Scheduled Scan"
SCHEDULED_SCAN_FLAG: str = "--scheduled-scan"

#: Supported frequencies mapped to ``schtasks /SC`` values.
FREQUENCIES: dict[str, str] = {"Daily": "DAILY", "Weekly": "WEEKLY"}

_TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class SchedulerError(Exception):
    """Raised when a schedule cannot be installed, removed, or queried."""


@dataclass(frozen=True)
class ScheduleConfig:
    """A validated schedule: frequency (``Daily``/``Weekly``) and 24h ``HH:MM`` time."""

    frequency: str = "Daily"
    time: str = "02:00"

    def __post_init__(self) -> None:
        if self.frequency not in FREQUENCIES:
            raise ValueError(f"Unsupported frequency {self.frequency!r}; expected one of {sorted(FREQUENCIES)}.")
        if not _TIME_PATTERN.match(self.time):
            raise ValueError(f"Invalid time {self.time!r}; expected 24-hour HH:MM.")


def default_launch_command() -> list[str]:
    """Return the command Task Scheduler should run.

    For a PyInstaller-frozen build this is the executable itself; in a
    development checkout it is the current interpreter running ``app.py``.
    """
    if getattr(sys, "frozen", False):
        return [sys.executable, SCHEDULED_SCAN_FLAG]
    app_py = Path(__file__).resolve().parent.parent / "app.py"
    return [sys.executable, str(app_py), SCHEDULED_SCAN_FLAG]


def _quote(arg: str) -> str:
    return f'"{arg}"' if (" " in arg and not arg.startswith('"')) else arg


def build_create_command(config: ScheduleConfig, launch_command: Sequence[str] | None = None) -> list[str]:
    """Return the ``schtasks /Create`` argument list for ``config``."""
    launch = list(launch_command) if launch_command is not None else default_launch_command()
    task_run = " ".join(_quote(part) for part in launch)
    return [
        "schtasks", "/Create", "/F",
        "/TN", TASK_NAME,
        "/SC", FREQUENCIES[config.frequency],
        "/ST", config.time,
        "/TR", task_run,
    ]


def build_delete_command() -> list[str]:
    return ["schtasks", "/Delete", "/F", "/TN", TASK_NAME]


def build_query_command() -> list[str]:
    return ["schtasks", "/Query", "/TN", TASK_NAME]


def _execute(command: list[str], runner: Runner | None) -> "subprocess.CompletedProcess[str]":
    if runner is None:
        if not sys.platform.startswith("win"):
            raise SchedulerError("Scheduled scanning requires Windows Task Scheduler.")
        runner = subprocess.run
    try:
        return runner(command, capture_output=True, text=True, check=False)
    except OSError as error:
        raise SchedulerError(f"Could not run schtasks: {error}") from error


def install_schedule(
    config: ScheduleConfig,
    runner: Runner | None = None,
    launch_command: Sequence[str] | None = None,
) -> None:
    """Create (or replace) the scheduled scan task."""
    completed = _execute(build_create_command(config, launch_command), runner)
    if completed.returncode != 0:
        raise SchedulerError((completed.stderr or completed.stdout or "schtasks failed").strip())
    logger.info("Scheduled scan installed: %s at %s.", config.frequency, config.time)


def remove_schedule(runner: Runner | None = None) -> None:
    """Delete the scheduled scan task if present."""
    completed = _execute(build_delete_command(), runner)
    if completed.returncode != 0:
        raise SchedulerError((completed.stderr or completed.stdout or "schtasks failed").strip())
    logger.info("Scheduled scan removed.")


def is_schedule_installed(runner: Runner | None = None) -> bool:
    """Return True if the scheduled scan task exists."""
    return _execute(build_query_command(), runner).returncode == 0


@dataclass(frozen=True)
class ScheduledScanOutcome:
    """Result of scanning one monitored folder during a scheduled run."""

    root_directory: str
    scan_id: int | None
    summary: ScanSummary | None
    report_path: Path | None
    error: str | None = None


def run_scheduled_scan(db_path: Path, exports_dir: Path) -> list[ScheduledScanOutcome]:
    """Scan every baselined folder against its latest baseline (headless).

    A failure on one folder (e.g. it was deleted) is logged and recorded
    in its outcome; remaining folders are still scanned.
    """
    outcomes: list[ScheduledScanOutcome] = []
    with connect(db_path) as connection:
        directories = repository.list_baseline_directories(connection)
        if not directories:
            logger.info("Scheduled scan: no baselines exist; nothing to scan.")
        for root in directories:
            try:
                baseline = find_baseline_for_directory(connection, root)
                if baseline is None or baseline.baseline_id is None:
                    raise LookupError("no baseline found")
                started_at = datetime.now(timezone.utc).isoformat()
                results = run_scan(baseline)
                scan_id = save_scan(connection, baseline.baseline_id, started_at, results)
                connection.commit()
                report = export_json(
                    results,
                    Path(exports_dir) / default_export_filename(scan_id, started_at, "json"),
                    scan_id=scan_id,
                    timestamp=started_at,
                    root_directory=root,
                )
                outcomes.append(ScheduledScanOutcome(root, scan_id, ScanSummary.from_results(results), report))
            except Exception as error:  # noqa: BLE001 - one bad folder must not stop the rest
                logger.exception("Scheduled scan of %s failed.", root)
                outcomes.append(ScheduledScanOutcome(root, None, None, None, str(error)))
    return outcomes
