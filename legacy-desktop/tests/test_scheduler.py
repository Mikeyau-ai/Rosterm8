"""Unit tests for the deterministic scheduler.

These are the guarantees the app is sold on - fairness, availability, clashes
and honest reporting of what could not be filled - so each gets a test.
"""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.models import Person, ShiftType                    # noqa: E402
from core.scheduler import build_roster, date_range, format_table  # noqa: E402

ALL_DAYS = set(range(7))
WEEKDAYS = {0, 1, 2, 3, 4}


def person(pid: int, name: str, days: set[int] = None, **kw) -> Person:
    """Build a test person, available every day unless told otherwise."""
    p = Person(pid, 1, name, **kw)
    p.available_weekdays = ALL_DAYS if days is None else days
    return p


def shift(sid: int, name: str, headcount: int = 1, order: int = 0) -> ShiftType:
    """Build a test shift type."""
    return ShiftType(sid, 1, name, "", "", headcount, order)


class DateRangeTests(unittest.TestCase):
    """date_range() day selection."""

    def test_filters_to_selected_weekdays(self):
        """Only the chosen weekdays come back, in order."""
        # 1 Jun 2026 is a Monday.
        days = date_range(date(2026, 6, 1), date(2026, 6, 14), WEEKDAYS)
        self.assertEqual(len(days), 10)
        self.assertTrue(all(d.weekday() < 5 for d in days))
        self.assertEqual(days, sorted(days))

    def test_swapped_bounds_are_tolerated(self):
        """Passing end before start still yields the range."""
        self.assertEqual(
            date_range(date(2026, 6, 5), date(2026, 6, 1), ALL_DAYS),
            date_range(date(2026, 6, 1), date(2026, 6, 5), ALL_DAYS),
        )


class FairnessTests(unittest.TestCase):
    """Shift distribution across the roster period."""

    def test_shifts_are_spread_evenly(self):
        """With 4 interchangeable staff over 8 single-cover days, each gets 2."""
        people = [person(i, n) for i, n in
                  enumerate(["Alice", "Bob", "Carol", "Dave"], start=1)]
        r = build_roster(1, "t", people, [shift(1, "Day", 1)], [],
                         date(2026, 6, 1), date(2026, 6, 8), ALL_DAYS)
        self.assertEqual(sorted(r.counts().values()), [2, 2, 2, 2])

    def test_output_is_deterministic(self):
        """The same inputs produce byte-identical assignments every run."""
        def make():
            people = [person(i, n) for i, n in
                      enumerate(["Alice", "Bob", "Carol"], start=1)]
            return build_roster(1, "t", people, [shift(1, "Day", 2)], [],
                                date(2026, 6, 1), date(2026, 6, 10), ALL_DAYS)

        a, b = make(), make()
        self.assertEqual([(x.work_date, x.person_id) for x in a.assignments],
                         [(x.work_date, x.person_id) for x in b.assignments])

    def test_max_shifts_is_respected(self):
        """A per-person cap is never exceeded."""
        people = [person(1, "Alice", max_shifts=2), person(2, "Bob")]
        r = build_roster(1, "t", people, [shift(1, "Day", 1)], [],
                         date(2026, 6, 1), date(2026, 6, 10), ALL_DAYS)
        self.assertLessEqual(r.counts().get(1, 0), 2)


class ConstraintTests(unittest.TestCase):
    """Availability, blackouts and clash rules."""

    def test_weekday_availability_is_honoured(self):
        """Someone marked weekends-only never appears on a weekday."""
        weekend_only = person(1, "Alice", days={5, 6})
        r = build_roster(1, "t", [weekend_only, person(2, "Bob")],
                         [shift(1, "Day", 1)], [],
                         date(2026, 6, 1), date(2026, 6, 14), ALL_DAYS)
        alice_days = [a.work_date for a in r.assignments if a.person_id == 1]
        self.assertTrue(all(d.weekday() >= 5 for d in alice_days))
        self.assertTrue(alice_days, "Alice should still get her weekends")

    def test_blackout_dates_are_honoured(self):
        """A blackout range blocks those dates even on an available weekday."""
        alice = person(1, "Alice")
        alice.blackouts = [(date(2026, 6, 3), date(2026, 6, 5))]
        r = build_roster(1, "t", [alice, person(2, "Bob")],
                         [shift(1, "Day", 1)], [],
                         date(2026, 6, 1), date(2026, 6, 10), ALL_DAYS)
        blocked = {date(2026, 6, 3), date(2026, 6, 4), date(2026, 6, 5)}
        self.assertFalse(
            [a for a in r.assignments if a.person_id == 1 and a.work_date in blocked])

    def test_clashing_pair_never_share_a_shift(self):
        """Two people flagged as a clash are never on the same shift together."""
        people = [person(i, n) for i, n in
                  enumerate(["Alice", "Bob", "Carol", "Dave"], start=1)]
        r = build_roster(1, "t", people, [shift(1, "Day", 2)], [(1, 2)],
                         date(2026, 6, 1), date(2026, 6, 14), ALL_DAYS)
        by_shift: dict[tuple, set[int]] = {}
        for a in r.assignments:
            by_shift.setdefault((a.work_date, a.shift_type_id), set()).add(a.person_id)
        for crew in by_shift.values():
            self.assertFalse({1, 2} <= crew, "Alice and Bob were rostered together")

    def test_one_shift_per_person_per_day(self):
        """Nobody is placed on two shifts on the same date."""
        people = [person(i, n) for i, n in
                  enumerate(["Alice", "Bob", "Carol"], start=1)]
        shifts = [shift(1, "Early", 1, 0), shift(2, "Late", 1, 1)]
        r = build_roster(1, "t", people, shifts, [],
                         date(2026, 6, 1), date(2026, 6, 7), ALL_DAYS)
        seen: set[tuple] = set()
        for a in r.assignments:
            key = (a.work_date, a.person_id)
            self.assertNotIn(key, seen)
            seen.add(key)


class ReportingTests(unittest.TestCase):
    """The scheduler must say so when it cannot satisfy the request."""

    def test_shortfall_is_flagged(self):
        """Asking for more cover than there are staff produces a note per day."""
        r = build_roster(1, "t", [person(1, "Alice")], [shift(1, "Day", 3)], [],
                         date(2026, 6, 1), date(2026, 6, 2), ALL_DAYS)
        self.assertEqual(len(r.notes), 2)
        self.assertIn("only 1 of 3 filled", r.notes[0])

    def test_unused_person_is_flagged(self):
        """Someone with no availability at all is reported, not silently dropped."""
        ghost = person(1, "Ghost", days=set())
        r = build_roster(1, "t", [ghost, person(2, "Bob")],
                         [shift(1, "Day", 1)], [],
                         date(2026, 6, 1), date(2026, 6, 5), ALL_DAYS)
        self.assertTrue(any("Ghost was not rostered" in n for n in r.notes))

    def test_empty_inputs_do_not_crash(self):
        """No staff / no shifts / no days each return a roster carrying a note."""
        for people, shifts, days in (
            ([], [shift(1, "Day", 1)], ALL_DAYS),
            ([person(1, "Alice")], [], ALL_DAYS),
            ([person(1, "Alice")], [shift(1, "Day", 1)], set()),
        ):
            r = build_roster(1, "t", people, shifts, [],
                             date(2026, 6, 1), date(2026, 6, 5), days)
            self.assertEqual(r.assignments, [])
            self.assertTrue(r.notes)


class FormatTests(unittest.TestCase):
    """The monospace table used in the app and in exports."""

    def test_table_contains_headers_names_and_summary(self):
        """A rendered roster shows its columns, its people and the summary."""
        people = [person(1, "Alice"), person(2, "Bob")]
        shifts = [shift(1, "Early", 1, 0), shift(2, "Late", 1, 1)]
        r = build_roster(1, "t", people, shifts, [],
                         date(2026, 6, 1), date(2026, 6, 5), WEEKDAYS)
        text = format_table(r, people, shifts)
        self.assertIn("Date", text)
        self.assertIn("Early", text)
        self.assertIn("Alice", text)
        self.assertIn("Summary", text)


if __name__ == "__main__":
    unittest.main()
