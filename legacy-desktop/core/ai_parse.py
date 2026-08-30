"""Optional AI assist: turn free-text availability notes into structured rules.

The scheduler itself is entirely deterministic and never calls out to a model.
This module exists only for data entry: it takes the kind of note a manager
actually writes -

    Alice: Mon-Fri only
    Bob is away 5-9 June
    Don't put Carol and Dave on together

- and proposes structured edits (weekday patterns, blackout ranges, clash
pairs) which the GUI shows for approval before anything is saved. The model
never decides who works when; it only reads English.

Every result is validated against the organization's real staff list, so a
hallucinated name is dropped rather than written to the database.

The API key lives in the OS credential store (see :mod:`core.settings_store`),
never in the database or the project folder.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date

import requests

log = logging.getLogger(__name__)

#: Supported providers -> (endpoint template, default model). All three speak
#: JSON over plain HTTPS, so no vendor SDKs are needed.
PROVIDERS = {
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/models/"
               "{model}:generateContent", "gemini-2.5-flash"),
    "anthropic": ("https://api.anthropic.com/v1/messages", "claude-sonnet-5"),
    "openai": ("https://api.openai.com/v1/chat/completions", "gpt-4o-mini"),
}

_PROMPT = """You convert free-text staff availability notes into JSON. \
Output JSON only - no prose, no code fence.

The staff are exactly: {names}
Never invent a name that is not in that list.
The roster period is {start} to {end}.

Schema:
{{
  "people": [
    {{"name": "<exact name from the list>",
      "weekdays": [0-6, Monday=0, omit if the note says nothing about weekdays],
      "blackouts": [{{"start": "YYYY-MM-DD", "end": "YYYY-MM-DD", "reason": "..."}}]
    }}
  ],
  "clashes": [["<name>", "<name>"]]
}}

Rules:
- "weekdays" is the FULL set of days that person can work, not a diff.
- A single unavailable day is a blackout with start == end.
- Resolve relative dates against the roster period above; assume its year.
- Only include a person if the note actually says something about them.
- "clashes" is for pairs who must not share a shift.

Notes to convert:
{text}"""


class AIError(RuntimeError):
    """Raised when the provider call fails or returns something unusable."""


def _extract_json(text: str) -> dict:
    """Pull the JSON object out of a model reply, tolerating code fences."""
    text = text.strip()
    # Models wrap JSON in ```json ... ``` often enough to be worth handling.
    fence = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise AIError("The model did not return any JSON.")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise AIError(f"The model returned malformed JSON: {exc}") from exc


def _call(provider: str, model: str, api_key: str, prompt: str,
          timeout: int = 60) -> str:
    """POST the prompt to one provider and return the raw reply text."""
    if provider not in PROVIDERS:
        raise AIError(f"Unknown AI provider '{provider}'.")
    url_tpl, default_model = PROVIDERS[provider]
    model = model or default_model
    url = url_tpl.format(model=model)

    # Each provider wants a different envelope; the prompt itself is identical.
    if provider == "gemini":
        headers = {"x-goog-api-key": api_key}
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
    elif provider == "anthropic":
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
        payload = {"model": model, "max_tokens": 4096,
                   "messages": [{"role": "user", "content": prompt}]}
    else:  # openai and any OpenAI-compatible endpoint
        headers = {"Authorization": f"Bearer {api_key}"}
        payload = {"model": model,
                   "messages": [{"role": "user", "content": prompt}]}

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise AIError(f"Could not reach the AI provider: {exc}") from exc
    if r.status_code >= 400:
        raise AIError(f"AI provider returned {r.status_code}: {r.text[:300]}")

    data = r.json()
    try:
        if provider == "gemini":
            return data["candidates"][0]["content"]["parts"][0]["text"]
        if provider == "anthropic":
            return data["content"][0]["text"]
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AIError(f"Unexpected reply shape from {provider}.") from exc


def parse_availability(text: str, names: list[str], start: date, end: date,
                       provider: str, model: str, api_key: str) -> dict:
    """Convert free-text notes into structured, validated availability edits.

    Returns ``{"people": [...], "clashes": [[a, b], ...]}`` where every name is
    guaranteed to be one of ``names`` and every date is a real ``date``. Raises
    :class:`AIError` if the provider call or the reply cannot be used.
    """
    if not text.strip():
        return {"people": [], "clashes": []}
    if not api_key:
        raise AIError("No API key set - add one in Settings, or enter "
                      "availability manually on the Staff tab.")

    raw = _call(provider, model, api_key, _PROMPT.format(
        names=", ".join(names), start=start.isoformat(),
        end=end.isoformat(), text=text.strip()))
    return _validate(_extract_json(raw), names)


def _validate(data: dict, names: list[str]) -> dict:
    """Drop anything the model got wrong: unknown names, bad dates, bad weekdays.

    A model that hallucinates is a nuisance, not a data-integrity problem, so
    the policy here is to discard silently-invalid entries rather than fail the
    whole parse - the user reviews the proposed changes before they are saved.
    """
    # Case-insensitive lookup back to the canonical spelling of each name.
    canon = {n.lower(): n for n in names}
    out_people: list[dict] = []

    for entry in data.get("people") or []:
        if not isinstance(entry, dict):
            continue
        name = canon.get(str(entry.get("name", "")).strip().lower())
        if not name:
            log.info("[AI] dropping unknown name %r", entry.get("name"))
            continue

        clean: dict = {"name": name}

        # Weekdays: keep only real 0-6 indices, and only if some survived.
        if isinstance(entry.get("weekdays"), list):
            days = {int(d) for d in entry["weekdays"]
                    if isinstance(d, (int, float)) and 0 <= int(d) <= 6}
            if days:
                clean["weekdays"] = sorted(days)

        blackouts: list[dict] = []
        for b in entry.get("blackouts") or []:
            if not isinstance(b, dict):
                continue
            try:
                s = date.fromisoformat(str(b.get("start", "")).strip())
                e = date.fromisoformat(str(b.get("end", b.get("start", ""))).strip())
            except ValueError:
                log.info("[AI] dropping unparseable blackout %r", b)
                continue
            if e < s:
                s, e = e, s
            blackouts.append({"start": s, "end": e,
                              "reason": str(b.get("reason", "")).strip()})
        if blackouts:
            clean["blackouts"] = blackouts

        # Only keep the person if the model actually said something about them.
        if len(clean) > 1:
            out_people.append(clean)

    out_clashes: list[list[str]] = []
    for pair in data.get("clashes") or []:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            continue
        a = canon.get(str(pair[0]).strip().lower())
        b = canon.get(str(pair[1]).strip().lower())
        if a and b and a != b and [a, b] not in out_clashes and [b, a] not in out_clashes:
            out_clashes.append([a, b])

    return {"people": out_people, "clashes": out_clashes}


def describe(result: dict) -> str:
    """Render a parse result as the plain-English preview shown for approval."""
    lines: list[str] = []
    for p in result.get("people", []):
        if "weekdays" in p:
            from config import WEEKDAYS_SHORT
            days = ", ".join(WEEKDAYS_SHORT[d] for d in p["weekdays"])
            lines.append(f"{p['name']}: available {days}")
        for b in p.get("blackouts", []):
            span = (b["start"].strftime("%d %b")
                    if b["start"] == b["end"]
                    else f"{b['start']:%d %b} - {b['end']:%d %b}")
            reason = f" ({b['reason']})" if b["reason"] else ""
            lines.append(f"{p['name']}: unavailable {span}{reason}")
    for a, b in result.get("clashes", []):
        lines.append(f"{a} + {b}: never on the same shift")
    return "\n".join(lines) or "Nothing recognisable in those notes."
