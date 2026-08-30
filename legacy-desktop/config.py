r"""Global paths and constants for Rosterm8.

Everything the app persists lives under %LOCALAPPDATA%\Rosterm8 so the project
folder stays clean and the data survives a code update. Mirrors the InvoiceM8
layout so the two apps behave the same way on disk.
"""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "Rosterm8"

# Base data directory (created on first run).
if os.name == "nt":
    _base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
else:  # allow running/tests on non-Windows
    _base = Path.home() / ".local" / "share"

DATA_DIR = _base / APP_NAME
DB_PATH = DATA_DIR / "rosterm8.sqlite3"
EXPORT_DIR = DATA_DIR / "exports"
LOG_DIR = DATA_DIR / "logs"

#: keyring service under which the AI provider API key is stored (DPAPI-backed
#: on Windows). The key is the only secret this app holds, so it goes straight
#: into the OS credential store rather than an encrypted blob in the database.
KEYRING_SERVICE = "Rosterm8-ai-key"
KEYRING_USERNAME = "api-key"

#: Weekday names, Monday-first, indexed to match ``date.weekday()``.
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday",
            "Friday", "Saturday", "Sunday"]
WEEKDAYS_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def ensure_dirs() -> None:
    """Create all runtime directories. Safe to call repeatedly."""
    for d in (DATA_DIR, EXPORT_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)


def resource_path(name: str) -> Path:
    """Absolute path to a bundled asset, from source or a PyInstaller build.

    PyInstaller unpacks datas into ``sys._MEIPASS`` at runtime; running from
    source they sit next to this file.
    """
    import sys

    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


#: Window/taskbar icon - the same file PyInstaller stamps into the exe.
ICON_PATH = resource_path("assets/icon.ico")
