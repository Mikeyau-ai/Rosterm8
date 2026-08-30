"""SQLite storage for Rosterm8.

The data is organised in two layers: an **organization** owns everything, and
**people** (plus shift types, clash rules and rosters) belong to exactly one
organization. Switching org in the GUI therefore swaps the entire working set,
which is what lets one install serve several workplaces.

Schema changes go through :meth:`Database._migrate`, keyed on the SQLite
``user_version`` pragma, so an existing database upgrades in place.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

from core.models import Organization, Person, Roster, ShiftType

#: Bump when adding a migration step in ``_migrate``.
SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS organizations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS shift_types (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id      INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name        TEXT    NOT NULL,
    start_time  TEXT    NOT NULL DEFAULT '',
    end_time    TEXT    NOT NULL DEFAULT '',
    headcount   INTEGER NOT NULL DEFAULT 1,
    sort_order  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS people (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id      INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name        TEXT    NOT NULL,
    active      INTEGER NOT NULL DEFAULT 1,
    max_shifts  INTEGER,
    notes       TEXT    NOT NULL DEFAULT ''
);

-- One row per weekday a person is normally available. Absence of a row means
-- unavailable, so a person with no rows is never rostered.
CREATE TABLE IF NOT EXISTS availability (
    person_id   INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    weekday     INTEGER NOT NULL,
    PRIMARY KEY (person_id, weekday)
);

-- Inclusive date ranges a person cannot work regardless of the weekly pattern.
CREATE TABLE IF NOT EXISTS blackouts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id   INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    start_date  TEXT    NOT NULL,
    end_date    TEXT    NOT NULL,
    reason      TEXT    NOT NULL DEFAULT ''
);

-- "These two must not share a shift". Stored with person_a < person_b so the
-- pair is unordered and cannot be duplicated in both directions.
CREATE TABLE IF NOT EXISTS clashes (
    org_id      INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    person_a    INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    person_b    INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    PRIMARY KEY (person_a, person_b)
);

CREATE TABLE IF NOT EXISTS rosters (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id      INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name        TEXT    NOT NULL,
    start_date  TEXT    NOT NULL,
    end_date    TEXT    NOT NULL,
    created_at  TEXT    NOT NULL,
    notes       TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS assignments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    roster_id     INTEGER NOT NULL REFERENCES rosters(id) ON DELETE CASCADE,
    work_date     TEXT    NOT NULL,
    shift_type_id INTEGER NOT NULL,
    person_id     INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_people_org    ON people(org_id);
CREATE INDEX IF NOT EXISTS ix_shifts_org    ON shift_types(org_id);
CREATE INDEX IF NOT EXISTS ix_rosters_org   ON rosters(org_id);
CREATE INDEX IF NOT EXISTS ix_assign_roster ON assignments(roster_id);
"""


def _d(text: str) -> date:
    """Parse an ISO date string out of the database."""
    return date.fromisoformat(text)


class Database:
    """Owns the SQLite connection and every read/write the app performs."""

    def __init__(self, path: Path) -> None:
        """Open (creating if needed) the database at ``path`` and migrate it."""
        path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: the GUI thread and the generate/export work
        # both touch the DB. All writes are short and serialised by the GIL plus
        # SQLite's own locking, so one shared connection is enough.
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(_SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """Apply schema upgrades for databases created by an older version."""
        current = self.conn.execute("PRAGMA user_version").fetchone()[0]
        # No migrations yet - v1 is the initial schema created by _SCHEMA above.
        if current != SCHEMA_VERSION:
            self.conn.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)

    def close(self) -> None:
        """Commit and close. Safe to call more than once."""
        try:
            self.conn.commit()
            self.conn.close()
        except sqlite3.Error:
            pass

    # ---------------------------------------------------------------- orgs --
    def organizations(self) -> list[Organization]:
        """Every organization, alphabetically."""
        rows = self.conn.execute(
            "SELECT id, name FROM organizations ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [Organization(r["id"], r["name"]) for r in rows]

    def add_organization(self, name: str) -> int:
        """Create an organization and return its new id."""
        cur = self.conn.execute(
            "INSERT INTO organizations (name, created_at) VALUES (?, ?)",
            (name.strip(), datetime.now().isoformat(timespec="seconds")),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def rename_organization(self, org_id: int, name: str) -> None:
        """Rename an organization in place."""
        self.conn.execute("UPDATE organizations SET name = ? WHERE id = ?",
                          (name.strip(), org_id))
        self.conn.commit()

    def delete_organization(self, org_id: int) -> None:
        """Delete an organization and, by cascade, everything inside it."""
        self.conn.execute("DELETE FROM organizations WHERE id = ?", (org_id,))
        self.conn.commit()

    # -------------------------------------------------------------- shifts --
    def shift_types(self, org_id: int) -> list[ShiftType]:
        """An organization's shift types in allocation order."""
        rows = self.conn.execute(
            "SELECT * FROM shift_types WHERE org_id = ? ORDER BY sort_order, id",
            (org_id,),
        ).fetchall()
        return [ShiftType(r["id"], r["org_id"], r["name"], r["start_time"],
                          r["end_time"], r["headcount"], r["sort_order"])
                for r in rows]

    def save_shift_type(self, shift: ShiftType) -> int:
        """Insert (id <= 0) or update a shift type; returns its id."""
        if shift.id and shift.id > 0:
            self.conn.execute(
                "UPDATE shift_types SET name=?, start_time=?, end_time=?, "
                "headcount=?, sort_order=? WHERE id=?",
                (shift.name, shift.start_time, shift.end_time,
                 shift.headcount, shift.sort_order, shift.id),
            )
            new_id = shift.id
        else:
            cur = self.conn.execute(
                "INSERT INTO shift_types (org_id, name, start_time, end_time, "
                "headcount, sort_order) VALUES (?, ?, ?, ?, ?, ?)",
                (shift.org_id, shift.name, shift.start_time, shift.end_time,
                 shift.headcount, shift.sort_order),
            )
            new_id = int(cur.lastrowid)
        self.conn.commit()
        return new_id

    def delete_shift_type(self, shift_id: int) -> None:
        """Remove a shift type. Past rosters keep their rows and show the id."""
        self.conn.execute("DELETE FROM shift_types WHERE id = ?", (shift_id,))
        self.conn.commit()

    # -------------------------------------------------------------- people --
    def people(self, org_id: int, active_only: bool = False) -> list[Person]:
        """An organization's staff, each with availability and blackouts loaded."""
        sql = "SELECT * FROM people WHERE org_id = ?"
        if active_only:
            sql += " AND active = 1"
        sql += " ORDER BY name COLLATE NOCASE"
        rows = self.conn.execute(sql, (org_id,)).fetchall()

        out: list[Person] = []
        for r in rows:
            p = Person(r["id"], r["org_id"], r["name"], bool(r["active"]),
                       r["notes"], max_shifts=r["max_shifts"])
            p.available_weekdays = {
                w[0] for w in self.conn.execute(
                    "SELECT weekday FROM availability WHERE person_id = ?", (p.id,))
            }
            p.blackouts = [
                (_d(b["start_date"]), _d(b["end_date"]))
                for b in self.conn.execute(
                    "SELECT start_date, end_date FROM blackouts "
                    "WHERE person_id = ? ORDER BY start_date", (p.id,))
            ]
            out.append(p)
        return out

    def save_person(self, person: Person) -> int:
        """Insert or update a person together with their availability rows."""
        if person.id and person.id > 0:
            self.conn.execute(
                "UPDATE people SET name=?, active=?, max_shifts=?, notes=? WHERE id=?",
                (person.name, int(person.active), person.max_shifts,
                 person.notes, person.id),
            )
            pid = person.id
        else:
            cur = self.conn.execute(
                "INSERT INTO people (org_id, name, active, max_shifts, notes) "
                "VALUES (?, ?, ?, ?, ?)",
                (person.org_id, person.name, int(person.active),
                 person.max_shifts, person.notes),
            )
            pid = int(cur.lastrowid)

        # Availability is replaced wholesale - simpler and safer than diffing,
        # and the row count is at most seven.
        self.conn.execute("DELETE FROM availability WHERE person_id = ?", (pid,))
        self.conn.executemany(
            "INSERT INTO availability (person_id, weekday) VALUES (?, ?)",
            [(pid, w) for w in sorted(person.available_weekdays)],
        )
        self.conn.commit()
        return pid

    def delete_person(self, person_id: int) -> None:
        """Remove a person, their availability, blackouts and clash rules."""
        self.conn.execute("DELETE FROM people WHERE id = ?", (person_id,))
        self.conn.commit()

    # ----------------------------------------------------------- blackouts --
    def add_blackout(self, person_id: int, start: date, end: date,
                     reason: str = "") -> None:
        """Mark a person unavailable across an inclusive date range."""
        if end < start:
            start, end = end, start
        self.conn.execute(
            "INSERT INTO blackouts (person_id, start_date, end_date, reason) "
            "VALUES (?, ?, ?, ?)",
            (person_id, start.isoformat(), end.isoformat(), reason),
        )
        self.conn.commit()

    def blackouts(self, person_id: int) -> list[tuple[int, date, date, str]]:
        """A person's blackout ranges as (id, start, end, reason), earliest first."""
        rows = self.conn.execute(
            "SELECT id, start_date, end_date, reason FROM blackouts "
            "WHERE person_id = ? ORDER BY start_date", (person_id,)
        ).fetchall()
        return [(r["id"], _d(r["start_date"]), _d(r["end_date"]), r["reason"])
                for r in rows]

    def delete_blackout(self, blackout_id: int) -> None:
        """Remove one blackout range."""
        self.conn.execute("DELETE FROM blackouts WHERE id = ?", (blackout_id,))
        self.conn.commit()

    # ------------------------------------------------------------- clashes --
    def clashes(self, org_id: int) -> list[tuple[int, int]]:
        """Person-id pairs that must never share a shift, normalised a < b."""
        rows = self.conn.execute(
            "SELECT person_a, person_b FROM clashes WHERE org_id = ?", (org_id,)
        ).fetchall()
        return [(r["person_a"], r["person_b"]) for r in rows]

    def add_clash(self, org_id: int, a: int, b: int) -> None:
        """Record that two people must not share a shift. Ignores duplicates."""
        if a == b:
            return
        lo, hi = (a, b) if a < b else (b, a)
        self.conn.execute(
            "INSERT OR IGNORE INTO clashes (org_id, person_a, person_b) "
            "VALUES (?, ?, ?)", (org_id, lo, hi))
        self.conn.commit()

    def delete_clash(self, a: int, b: int) -> None:
        """Remove a clash rule, whichever order the pair is given in."""
        lo, hi = (a, b) if a < b else (b, a)
        self.conn.execute(
            "DELETE FROM clashes WHERE person_a = ? AND person_b = ?", (lo, hi))
        self.conn.commit()

    # ------------------------------------------------------------- rosters --
    def save_roster(self, roster: Roster) -> int:
        """Persist a generated roster and all of its assignments; returns its id."""
        cur = self.conn.execute(
            "INSERT INTO rosters (org_id, name, start_date, end_date, "
            "created_at, notes) VALUES (?, ?, ?, ?, ?, ?)",
            (roster.org_id, roster.name, roster.start_date.isoformat(),
             roster.end_date.isoformat(),
             datetime.now().isoformat(timespec="seconds"),
             "\n".join(roster.notes)),
        )
        rid = int(cur.lastrowid)
        self.conn.executemany(
            "INSERT INTO assignments (roster_id, work_date, shift_type_id, "
            "person_id) VALUES (?, ?, ?, ?)",
            [(rid, a.work_date.isoformat(), a.shift_type_id, a.person_id)
             for a in roster.assignments],
        )
        self.conn.commit()
        return rid

    def roster_history(self, org_id: int) -> list[sqlite3.Row]:
        """Saved rosters for an organization, newest first."""
        return self.conn.execute(
            "SELECT id, name, start_date, end_date, created_at, notes "
            "FROM rosters WHERE org_id = ? ORDER BY created_at DESC", (org_id,)
        ).fetchall()

    def load_roster(self, roster_id: int) -> Roster | None:
        """Rebuild a saved :class:`Roster` from the database, or None if gone."""
        from core.models import Assignment

        r = self.conn.execute("SELECT * FROM rosters WHERE id = ?",
                              (roster_id,)).fetchone()
        if r is None:
            return None
        roster = Roster(
            org_id=r["org_id"], name=r["name"],
            start_date=_d(r["start_date"]), end_date=_d(r["end_date"]),
            notes=[n for n in r["notes"].splitlines() if n.strip()],
        )
        roster.assignments = [
            Assignment(_d(a["work_date"]), a["shift_type_id"], a["person_id"])
            for a in self.conn.execute(
                "SELECT work_date, shift_type_id, person_id FROM assignments "
                "WHERE roster_id = ? ORDER BY work_date, shift_type_id",
                (roster_id,))
        ]
        return roster

    def delete_roster(self, roster_id: int) -> None:
        """Delete a saved roster and its assignments."""
        self.conn.execute("DELETE FROM rosters WHERE id = ?", (roster_id,))
        self.conn.commit()

    # ------------------------------------------------------------ settings --
    def get_setting(self, key: str, default: str = "") -> str:
        """Read an app setting, returning ``default`` when unset."""
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?",
                                (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        """Write an app setting."""
        self.conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)))
        self.conn.commit()
