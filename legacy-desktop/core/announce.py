"""Discord release announcements for Rosterm8.

Posts a rich-embed message to a Discord channel via an incoming webhook when
a new version is published. The webhook URL is a secret: it is read from the
``ROSTERM8_DISCORD_WEBHOOK`` environment variable and must never be committed
to source control or hard-coded here.

Uses plain ``requests.post`` against Discord's webhook REST endpoint - no
discord.py dependency needed for a single fire-and-forget message.
"""
from __future__ import annotations

import os

import requests

#: Discord truncates embed descriptions well above this, but we keep our own
#: cap so a huge changelog entry never trips the API's real limit.
_MAX_DESCRIPTION = 3800

#: Rosterm8's signature purple (matches gui/theme.py's ACCENT), as a Discord
#: embed colour integer (0xRRGGBB).
_EMBED_COLOUR = 0xB06ED8


def _truncate(text: str, limit: int) -> str:
    """Cut ``text`` to at most ``limit`` chars, breaking on a line boundary.

    Cutting mid-sentence looks broken in a chat embed, so when the text is
    too long we back up to the last newline before the limit instead.
    """
    if len(text) <= limit:
        return text
    cut = text[:limit]
    last_newline = cut.rfind("\n")
    if last_newline > 0:
        cut = cut[:last_newline]
    return cut.rstrip() + "\n…"


def announce_release(version: str, notes: str, download_url: str,
                      webhook_url: str | None = None) -> bool:
    """Post a Discord embed announcing a new Rosterm8 release.

    Returns True only on a 2xx response from Discord. Returns False (never
    raises) if no webhook URL is configured or the request fails - a missed
    announcement should not block or fail the release itself.
    """
    webhook_url = webhook_url if webhook_url is not None else os.getenv(
        "ROSTERM8_DISCORD_WEBHOOK", "").strip()
    if not webhook_url:
        print("  [announce] ROSTERM8_DISCORD_WEBHOOK not set - skipping Discord post.")
        return False

    embed = {
        "title": f"Rosterm8 v{version} released",
        "url": download_url,
        "description": _truncate(notes or "", _MAX_DESCRIPTION),
        "color": _EMBED_COLOUR,
        "fields": [
            {"name": "Download", "value": f"[Rosterm8.exe]({download_url})"},
        ],
        "footer": {"text": "Rosterm8 - staff roster builder"},
    }

    try:
        resp = requests.post(webhook_url, json={"embeds": [embed]}, timeout=10)
    except requests.RequestException as exc:
        print(f"  [announce] Discord webhook request failed: {exc}")
        return False

    if 200 <= resp.status_code < 300:
        return True
    print(f"  [announce] Discord webhook returned {resp.status_code}: {resp.text[:300]}")
    return False
