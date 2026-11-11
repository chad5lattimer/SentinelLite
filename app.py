"""SentinelLite application entry point.

Bootstraps logging and launches the main window, or -- with
``--scheduled-scan`` -- runs a headless scheduled scan (section 20).
"""

from __future__ import annotations

import logging
import sys

from config import APP_NAME, APP_VERSION, PATHS, configure_logging
from gui.main_window import MainWindow

logger = logging.getLogger(__name__)


def run_headless_scheduled_scan() -> int:
    """Run the Task Scheduler job (``--scheduled-scan``) without a GUI.

    Returns 0 when every baselined folder scanned cleanly, 1 if any failed.
    """
    from core.scheduler import run_scheduled_scan

    outcomes = run_scheduled_scan(PATHS.database_path, PATHS.exports_dir)
    for outcome in outcomes:
        if outcome.error:
            logger.error("Scheduled scan failed for %s: %s", outcome.root_directory, outcome.error)
        else:
            logger.info("Scheduled scan #%s of %s -> %s", outcome.scan_id, outcome.root_directory, outcome.report_path)
    return 1 if any(outcome.error for outcome in outcomes) else 0


def main(argv: list[str] | None = None) -> int:
    """Configure logging, build the main window, and run the GUI event loop.

    With ``--scheduled-scan`` (used by Windows Task Scheduler, PROJECT_SPEC.md
    section 20) a headless scan runs instead and no window is opened.

    Returns a process exit code (0 on a normal, clean shutdown).
    """
    args = sys.argv[1:] if argv is None else argv
    log_file = configure_logging()
    logger.info("%s v%s starting up.", APP_NAME, APP_VERSION)
    logger.debug("Log file: %s", log_file)

    if "--scheduled-scan" in args:
        return run_headless_scheduled_scan()

    try:
        window = MainWindow()
    except Exception:
        logger.exception("Failed to create the main window.")
        raise

    try:
        window.mainloop()
    finally:
        logger.info("%s shutting down.", APP_NAME)

    return 0


if __name__ == "__main__":
    sys.exit(main())
