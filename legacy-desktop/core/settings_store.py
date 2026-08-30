"""App settings, with the AI API key held in the OS credential store.

Ordinary preferences (provider name, model, default shift pattern) are plain
rows in the ``settings`` table. The API key is the only secret Rosterm8 holds,
so it goes to ``keyring`` - DPAPI-backed on Windows - rather than the database.
"""
from __future__ import annotations

import logging

from config import KEYRING_SERVICE, KEYRING_USERNAME

log = logging.getLogger(__name__)

#: Defaults applied when a key has never been written.
DEFAULTS = {
    "ai.provider": "gemini",
    "ai.model": "",
    "last.org_id": "",
    "updates.auto_check": "1",
}


class Settings:
    """Typed accessors over the ``settings`` table plus the keyring."""

    def __init__(self, db) -> None:
        """Bind to an open :class:`core.database.Database`."""
        self.db = db

    def get(self, key: str, default: str | None = None) -> str:
        """Read a string setting, falling back to DEFAULTS then ``default``."""
        fallback = DEFAULTS.get(key, "" if default is None else default)
        return self.db.get_setting(key, fallback)

    def set(self, key: str, value) -> None:
        """Write a setting as a string."""
        self.db.set_setting(key, str(value))

    def get_bool(self, key: str) -> bool:
        """Read a setting as a boolean ('1'/'true'/'yes' are all true)."""
        return self.get(key).strip().lower() in ("1", "true", "yes", "on")

    def set_bool(self, key: str, value: bool) -> None:
        """Write a boolean setting."""
        self.set(key, "1" if value else "0")

    # ------------------------------------------------------------ API key --
    def api_key(self) -> str:
        """The AI provider key from the OS credential store, or "" if unset."""
        try:
            import keyring
            return keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME) or ""
        except Exception as exc:
            # A missing/blocked keyring backend must not stop the app booting -
            # everything except the optional AI assist works without a key.
            log.warning("Could not read the API key from the credential store: %s", exc)
            return ""

    def set_api_key(self, value: str) -> bool:
        """Store (or, given an empty string, delete) the AI provider key."""
        try:
            import keyring
            if value.strip():
                keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, value.strip())
            else:
                try:
                    keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
                except Exception:
                    pass        # nothing stored yet - deleting is a no-op
            return True
        except Exception as exc:
            log.error("Could not save the API key: %s", exc)
            return False
