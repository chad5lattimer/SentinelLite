"""Tests for core.scheduler -- optional scheduled scanning (PROJECT_SPEC.md section 20).

``schtasks`` is never actually executed: every install/remove/query call
goes through a fake runner, so these tests run on any platform.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from core import scheduler
from core.baseline import create_baseline, save_baseline
from core.scheduler import (
    SCHEDULED_SCAN_FLAG,
    TASK_NAME,
    ScheduleConfig,
    SchedulerError,
    build_create_command,
    build_delete_command,
    install_schedule,
    is_schedule_installed,
    remove_schedule,
    run_scheduled_scan,
)
from storage import repository
from storage.database import connect


class FakeRunner:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.calls = []
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, self.returncode, self.stdout, self.stderr)


# --- ScheduleConfig -------------------------------------------------------

def test_default_config_is_daily_at_2am():
    config = ScheduleConfig()
    assert (config.frequency, config.time) == ("Daily", "02:00")


@pytest.mark.parametrize("time", ["2:00", "24:00", "12:60", "noon", ""])
def test_invalid_time_rejected(time):
    with pytest.raises(ValueError):
        ScheduleConfig(time=time)


def test_invalid_frequency_rejected():
    with pytest.raises(ValueError):
        ScheduleConfig(frequency="Hourly")


# --- command builders -----------------------------------------------------

def test_create_command_uses_schtasks_with_frequency_time_and_flag():
    command = build_create_command(
        ScheduleConfig("Weekly", "23:30"), [r"C:\Program Files\SentinelLite\SentinelLite.exe", SCHEDULED_SCAN_FLAG]
    )
    assert command[:3] == ["schtasks", "/Create", "/F"]
    assert command[command.index("/TN") + 1] == TASK_NAME
    assert command[command.index("/SC") + 1] == "WEEKLY"
    assert command[command.index("/ST") + 1] == "23:30"
    assert command[command.index("/TR") + 1] == (
        r'"C:\Program Files\SentinelLite\SentinelLite.exe" --scheduled-scan'
    )


def test_default_launch_command_dev_checkout_runs_app_py(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    launch = scheduler.default_launch_command()
    assert launch[0] == sys.executable
    assert launch[1].endswith("app.py")
    assert launch[-1] == SCHEDULED_SCAN_FLAG


def test_default_launch_command_frozen_runs_executable(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert scheduler.default_launch_command() == [sys.executable, SCHEDULED_SCAN_FLAG]


def test_delete_command():
    assert build_delete_command() == ["schtasks", "/Delete", "/F", "/TN", TASK_NAME]


# --- install / remove / query --------------------------------------------

def test_install_schedule_runs_create_command():
    runner = FakeRunner()
    install_schedule(ScheduleConfig(), runner=runner, launch_command=["x.exe", SCHEDULED_SCAN_FLAG])
    (command, kwargs), = runner.calls
    assert command[1] == "/Create"
    assert kwargs["capture_output"] is True


def test_install_schedule_failure_raises_with_message():
    with pytest.raises(SchedulerError, match="Access is denied"):
        install_schedule(ScheduleConfig(), runner=FakeRunner(1, stderr="ERROR: Access is denied."), launch_command=["x"])


def test_remove_schedule_failure_raises():
    with pytest.raises(SchedulerError):
        remove_schedule(runner=FakeRunner(1, stderr="not found"))


def test_remove_schedule_success():
    runner = FakeRunner()
    remove_schedule(runner=runner)
    assert runner.calls[0][0] == build_delete_command()


def test_is_schedule_installed_reflects_return_code():
    assert is_schedule_installed(runner=FakeRunner(0)) is True
    assert is_schedule_installed(runner=FakeRunner(1)) is False


def test_runner_oserror_becomes_scheduler_error():
    def broken(*args, **kwargs):
        raise FileNotFoundError("schtasks")

    with pytest.raises(SchedulerError):
        is_schedule_installed(runner=broken)


def test_default_runner_refuses_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(SchedulerError, match="Windows"):
        is_schedule_installed()


# --- headless scheduled scan ---------------------------------------------

def _baseline(db_path, root):
    baseline, _ = create_baseline(root)
    with connect(db_path) as connection:
        save_baseline(connection, baseline)


def test_run_scheduled_scan_with_no_baselines(tmp_path):
    assert run_scheduled_scan(tmp_path / "db.sqlite", tmp_path / "exports") == []


def test_run_scheduled_scan_detects_changes_and_writes_report(tmp_path):
    root = tmp_path / "watched"
    root.mkdir()
    (root / "A.txt").write_text("a")
    (root / "B.txt").write_text("b")
    db_path = tmp_path / "db.sqlite"
    _baseline(db_path, root)

    (root / "A.txt").write_text("changed")
    (root / "B.txt").unlink()
    (root / "D.txt").write_text("d")

    outcomes = run_scheduled_scan(db_path, tmp_path / "exports")

    (outcome,) = outcomes
    assert outcome.error is None
    assert (outcome.summary.modified, outcome.summary.deleted, outcome.summary.new) == (1, 1, 1)
    payload = json.loads(outcome.report_path.read_text(encoding="utf-8"))
    assert payload["scan_id"] == outcome.scan_id
    assert payload["summary"]["modified"] == 1
    with connect(db_path) as connection:
        assert [scan.scan_id for scan in repository.list_scans(connection)] == [outcome.scan_id]


def test_run_scheduled_scan_continues_after_missing_folder(tmp_path):
    db_path = tmp_path / "db.sqlite"
    gone, kept = tmp_path / "gone", tmp_path / "kept"
    for folder in (gone, kept):
        folder.mkdir()
        (folder / "f.txt").write_text("x")
        _baseline(db_path, folder)
    for child in gone.iterdir():
        child.unlink()
    gone.rmdir()

    outcomes = run_scheduled_scan(db_path, tmp_path / "exports")

    assert [o.error is not None for o in outcomes] == [True, False]
    assert outcomes[1].summary.unchanged == 1


def test_list_baseline_directories_is_distinct(tmp_path):
    db_path = tmp_path / "db.sqlite"
    root = tmp_path / "r"
    root.mkdir()
    _baseline(db_path, root)
    _baseline(db_path, root)
    with connect(db_path) as connection:
        assert repository.list_baseline_directories(connection) == [str(root.resolve())]
