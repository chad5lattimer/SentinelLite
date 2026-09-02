"""Application configuration and metadata for SentinelLite.

This module centralizes:
    - Application metadata (name, version).
    - Filesystem locations for mutable application data (database, logs,
      exports), following the Windows-appropriate location described in
      PROJECT_SPEC.md section 22.
    - Logging configuration.
    - A small set of tunable defaults (e.g. hashing chunk size) that are
      shared across the `core` package.

Nothing in this module performs filesystem scanning or hashing; it only
prepares configuration and directories used by later components.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Application metadata
# ---------------------------------------------------------------------------

APP_NAME: str = "SentinelLite"
APP_VERSION: str = "0.1.0"
APP_DESCRIPTION: str = "File Integrity Monitor"

# ---------------------------------------------------------------------------
# Hashing defaults (used by core.hasher in a later run)
# ---------------------------------------------------------------------------

#: Default chunk size for incremental hashing (1 MiB), per PROJECT_SPEC.md
#: section 7.2. Kept here so it is configurable in one place.
DEFAULT_HASH_CHUNK_SIZE: int = 1024 * 1024


def _default_app_data_dir() -> Path:
    """Return the platform-appropriate, user-writable application data
    directory for SentinelLite.

    Per PROJECT_SPEC.md section 22, mutable application data must not be
    stored inside the installation directory when running as a packaged
    application. On Windows this resolves to::

        %LOCALAPPDATA%\\SentinelLite

    On non-Windows platforms (used for development and automated testing,
    since the packaged target is Windows-only) a sensible per-user
    equivalent is used instead.
    """
    override = os.environ.get("SENTINELLITE_DATA_DIR")
    if override:
        return Path(override).expanduser()

    if sys.platform.startswith("win"):
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        return base / APP_NAME

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME

    # Linux / other Unix-like (development and CI environments).
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg_data_home) if xdg_data_home else Path.home() / ".local" / "share"
    return base / APP_NAME


@dataclass(frozen=True)
class AppPaths:
    """Resolved, user-writable filesystem locations used by the application."""

    data_dir: Path
    logs_dir: Path
    exports_dir: Path
    database_path: Path
    log_file: Path

    @classmethod
    def resolve(cls, base_dir: Path | None = None) -> "AppPaths":
        base = base_dir if base_dir is not None else _default_app_data_dir()
        logs_dir = base / "logs"
        exports_dir = base / "exports"
        return cls(
            data_dir=base,
            logs_dir=logs_dir,
            exports_dir=exports_dir,
            database_path=base / "sentinellite.db",
            log_file=logs_dir / "sentinellite.log",
        )

    def ensure_directories(self) -> None:
        """Create the application data, logs, and exports directories if
        they do not already exist. Safe to call repeatedly."""
        for directory in (self.data_dir, self.logs_dir, self.exports_dir):
            directory.mkdir(parents=True, exist_ok=True)


# Resolved once at import time; individual tests may construct their own
# AppPaths pointing elsewhere via SENTINELLITE_DATA_DIR or AppPaths.resolve().
PATHS: AppPaths = AppPaths.resolve()


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_LOGGING_CONFIGURED = False


def configure_logging(paths: AppPaths | None = None, level: int = logging.INFO) -> Path:
    """Configure application-wide logging.

    Logs are written both to a rotating-free local log file (per
    PROJECT_SPEC.md section 16) and to stderr, which is useful during
    development. Safe to call multiple times; only the first call takes
    effect unless ``paths`` differs from the previously configured paths.

    Returns the path to the log file.
    """
    global _LOGGING_CONFIGURED

    resolved_paths = paths if paths is not None else PATHS
    resolved_paths.ensure_directories()

    root_logger = logging.getLogger()

    if not _LOGGING_CONFIGURED:
        root_logger.setLevel(level)

        file_handler = logging.FileHandler(resolved_paths.log_file, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        root_logger.addHandler(file_handler)

        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        root_logger.addHandler(stream_handler)

        _LOGGING_CONFIGURED = True

    return resolved_paths.log_file
