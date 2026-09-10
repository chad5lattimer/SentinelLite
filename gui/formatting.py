"""Small display-formatting helpers shared across the GUI package.

Kept separate (rather than duplicated in ``main_window.py`` and
``history_dialog.py``) per PROJECT_SPEC.md section 35's "avoid duplicate
implementations" guidance. Pure formatting -- no hashing, filesystem, or
storage logic.
"""

from __future__ import annotations

from datetime import datetime


def format_display_time(iso_timestamp: str) -> str:
    """Render an ISO-8601 timestamp as a friendly string, e.g. "Aug 26, 2026 12:31 AM"."""
    try:
        parsed = datetime.fromisoformat(iso_timestamp)
    except ValueError:
        return iso_timestamp
    return parsed.strftime("%b %d, %Y %I:%M %p")
