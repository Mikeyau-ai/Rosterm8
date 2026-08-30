"""Rosterm8 entry point.

    python main.py

A standalone staff-roster builder: organizations own their staff, shift types
and rosters, and the scheduler in :mod:`core.scheduler` allocates them.
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

import customtkinter as ctk

from config import DB_PATH, LOG_DIR, ensure_dirs
from core.database import Database
from core.settings_store import Settings
from gui import theme
from gui.app import App


def _setup_logging() -> None:
    """File + console logging for diagnostics.

    Rotating, because a desktop app that lives in the tray for months would
    otherwise grow its log file for the lifetime of the install.
    """
    ensure_dirs()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            RotatingFileHandler(LOG_DIR / "rosterm8.log", encoding="utf-8",
                                maxBytes=2_000_000, backupCount=3),
            logging.StreamHandler(sys.stdout),
        ],
    )


def main() -> None:
    """Build the database, settings and theme, then run the Tk event loop."""
    _setup_logging()

    db = Database(DB_PATH)
    settings = Settings(db)

    theme.apply(ctk)
    app = App(db, settings)
    try:
        app.mainloop()
    finally:
        # Belt-and-braces: _on_close normally closes the DB, but make sure it
        # happens even on an abnormal exit.
        db.close()


if __name__ == "__main__":
    main()
