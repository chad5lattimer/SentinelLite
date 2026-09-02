"""SentinelLite application entry point.

Run 1 scope: application bootstrap only -- logging setup and launching the
main window. Filesystem scanning, hashing, and baseline logic are
implemented in later runs and are intentionally absent here (see
PROJECT_SPEC.md sections 26-31 for the run-by-run plan).
"""

from __future__ import annotations

import logging
import sys

from config import APP_NAME, APP_VERSION, configure_logging
from gui.main_window import MainWindow

logger = logging.getLogger(__name__)


def main() -> int:
    """Configure logging, build the main window, and run the GUI event loop.

    Returns a process exit code (0 on a normal, clean shutdown).
    """
    log_file = configure_logging()
    logger.info("%s v%s starting up.", APP_NAME, APP_VERSION)
    logger.debug("Log file: %s", log_file)

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
