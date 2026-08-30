# Rosterm8

Local Windows desktop app for building staff rosters. One install can serve
several workplaces: an **organization** owns its own staff, shift types and
roster history, so switching org in the header swaps the entire working set.

Allocation is **deterministic** — a scheduler in `core/scheduler.py` spreads
shifts fairly, honours weekly availability, blackout dates and "these two must
not work together" clash rules, and reports anything it could not fill instead
of quietly fudging it. The same inputs always produce the same roster.

Split out of the Guardian Discord bot's `/roster` command, which asked an LLM
for an ASCII table and printed whatever came back.

Styled to match the RamBo and InvoiceM8 desktop utilities (same near-black
palette, Segoe UI / Consolas type, flat accent buttons — Rosterm8 takes the
purple).

## Install

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Python 3.11+ recommended.

## Build a standalone .exe

```bash
build.bat
```

Runs PyInstaller against `Rosterm8.spec` and produces a single windowed
`dist\Rosterm8.exe`. Settings and the database live in `%LOCALAPPDATA%\Rosterm8`,
so the exe stays stateless and can be replaced in place to update.

## Releasing updates

```bash
:: bump version.py, add a CHANGELOG.md section, commit, then:
release.bat
```

Builds the exe and publishes it as a GitHub release tagged `v<version>`.
Installed builds check `releases/latest` on launch (and via **Settings >
Updates**), download the new `Rosterm8.exe` and swap it in via a detached
helper. Running from source never prompts.

Permanent download link:
`https://github.com/Mikeyau-ai/Rosterm8/releases/latest/download/Rosterm8.exe`

### Announcing a release to Discord

`release.py --announce` posts a rich embed (version, changelog, download link)
to a Discord channel after the upload succeeds. It is **opt-in per invocation** —
without the flag nothing is posted. The webhook URL is read from the
`ROSTERM8_DISCORD_WEBHOOK` environment variable and must never be committed.

```bash
python release.py --announce
```

## First run

1. **+ Organization** in the header — create your workplace.
2. **Shifts tab** — define the shift types that workplace runs (e.g.
   `Early 06:00-14:00, needs 2`). At least one is required. Their order is the
   order the scheduler fills them in.
3. **Staff tab** — add people, tick the weekdays each can work, add blackout
   dates and any clash rules.
4. **Build Roster tab** — pick the dates and rostered weekdays, press
   **Build roster**, then save, copy or export it.

## Data location

`%LOCALAPPDATA%\Rosterm8\` — `rosterm8.sqlite3`, `exports\`, `logs\`.

## Module map

| Area          | Files |
|---------------|-------|
| Entry         | `main.py`, `config.py`, `version.py` |
| Data model    | `core/models.py`, `core/database.py` |
| Allocation    | `core/scheduler.py` |
| AI assist     | `core/ai_parse.py` (optional — parses availability notes only) |
| Settings      | `core/settings_store.py` |
| Updates       | `core/updater.py`, `gui/update_dialog.py`, `release.py` |
| Announcements | `core/announce.py` |
| GUI           | `gui/*` (CustomTkinter, shared theme in `gui/theme.py`) |
| Branding      | `make_icon.py` -> `assets/icon.ico`, `assets/logo.png` |
| Tests         | `tests/test_scheduler.py` |

## The AI assist is optional

The scheduler never calls a model. The only AI in the app converts free-text
availability notes ("Bob is away 5-9 June", "don't put Carol and Dave on
together") into structured rules, which are shown for approval before anything
is saved. Names the model invents are discarded. With no API key configured the
app works exactly the same — you just tick the availability boxes yourself.

Supported providers: Gemini, Anthropic, OpenAI (and OpenAI-compatible
endpoints). The key is held in the Windows Credential Manager, never in the
database or the project folder.

## Tests

```bash
python -m unittest discover -s tests
```

The scheduler's guarantees — fair distribution, availability, blackouts,
clashes, one shift per person per day, honest shortfall reporting and
determinism — each have a test. `release.py` refuses to publish if they fail.
