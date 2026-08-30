"""Deterministic roster allocation.

This is the part that replaces the Guardian bot's "send the constraints to an
LLM and print whatever comes back". Given the same inputs this module always
produces the same roster, every constraint it is given is actually enforced,
and anything it *cannot* satisfy is reported as an explicit note rather than
quietly fudged.

The algorithm is a greedy fill with a fairness ranking. Days are processed in
order; within a day, shifts are filled in the organization's own shift order.
For each vacancy the eligible pool is ranked by

    1. fewest shifts worked so far in this roster   (spread the load)
    2. longest since last worked                    (spread the days out)
    3. name                                         (a stable, arbitrary tiebreak)

and the top candidates are taken. Greedy rather than an exhaustive search
because rosters are small, the result must be explainable to the person reading
it ("Alice got Tuesday because she'd worked the fewest shifts"), and a solver
that silently reshuffles everything on a one-person change is worse to live
with than one that does the obvious thing.
"""
from __future__ import annotations

from datetime import date, timedelta

from core.models import Assignment, Person, Roster, ShiftType

#: Sentinel "has never worked" date used by the recency tiebreak. Any real date
#: sorts after it, so people who have not worked yet are always preferred.
_NEVER = date.min


def date_range(start: date, end: date, weekdays: set[int]) -> list[date]:
    """Every date from ``start`` to ``end`` inclusive whose weekday is rostered.

    ``weekdays`` holds ``date.weekday()`` values (0=Monday .. 6=Sunday); an
    empty set means no days at all, which the caller should treat as an error.
    """
    if end < start:
        start, end = end, start
    out: list[date] = []
    day = start
    while day <= end:
        if day.weekday() in weekdays:
            out.append(day)
        day += timedelta(days=1)
    return out


def _clash_map(clashes: list[tuple[int, int]]) -> dict[int, set[int]]:
    """Expand unordered clash pairs into a person-id -> incompatible-ids map."""
    out: dict[int, set[int]] = {}
    for a, b in clashes:
        out.setdefault(a, set()).add(b)
        out.setdefault(b, set()).add(a)
    return out


def build_roster(
    org_id: int,
    name: str,
    people: list[Person],
    shifts: list[ShiftType],
    clashes: list[tuple[int, int]],
    start: date,
    end: date,
    weekdays: set[int],
) -> Roster:
    """Allocate staff across the date range and return the finished roster.

    Anything that could not be satisfied - an unfillable shift, a person with
    no availability at all - is appended to ``roster.notes`` instead of being
    silently dropped, so the GUI can surface it next to the table.
    """
    days = date_range(start, end, weekdays)
    roster = Roster(org_id=org_id, name=name,
                    start_date=days[0] if days else start,
                    end_date=days[-1] if days else end)

    # Guard the degenerate inputs up front so the main loop can assume it has
    # something to work with.
    roster_people = [p for p in people if p.active]
    if not days:
        roster.notes.append("No rostered days fall in the selected date range.")
        return roster
    if not shifts:
        roster.notes.append("This organization has no shift types defined.")
        return roster
    if not roster_people:
        roster.notes.append("No active staff to roster.")
        return roster

    incompatible = _clash_map(clashes)

    # Running fairness state, keyed by person id.
    worked: dict[int, int] = {p.id: 0 for p in roster_people}
    last_worked: dict[int, date] = {p.id: _NEVER for p in roster_people}

    for day in days:
        # One shift per person per day: whoever is already on today is out of
        # the pool for the day's remaining shifts.
        used_today: set[int] = set()

        for shift in shifts:
            placed: list[Person] = []

            for _ in range(max(0, shift.headcount)):
                candidate = _pick(shift, day, roster_people, used_today, placed,
                                  incompatible, worked, last_worked)
                if candidate is None:
                    break
                placed.append(candidate)
                used_today.add(candidate.id)
                worked[candidate.id] += 1
                last_worked[candidate.id] = day
                roster.assignments.append(
                    Assignment(work_date=day, shift_type_id=shift.id,
                               person_id=candidate.id))

            # Report the gap rather than pretending the shift is covered.
            if len(placed) < shift.headcount:
                roster.notes.append(
                    f"{day.strftime('%a %d %b %Y')} - {shift.name}: "
                    f"only {len(placed)} of {shift.headcount} filled "
                    f"(nobody else was available)."
                )

    # Flag staff the roster never used, which is nearly always a data problem
    # (no availability ticked, or a blackout covering the whole period).
    for p in roster_people:
        if worked[p.id] == 0:
            reason = ("no weekdays ticked in their availability"
                      if not p.available_weekdays
                      else "unavailable on every rostered day")
            roster.notes.append(f"{p.name} was not rostered at all - {reason}.")

    return roster


def _pick(
    shift: ShiftType,
    day: date,
    people: list[Person],
    used_today: set[int],
    placed: list[Person],
    incompatible: dict[int, set[int]],
    worked: dict[int, int],
    last_worked: dict[int, date],
) -> Person | None:
    """Choose the fairest eligible person for one vacancy, or None if there is none."""
    placed_ids = {p.id for p in placed}

    eligible = [
        p for p in people
        if p.id not in used_today                       # not already on today
        and p.can_work(day)                             # availability + blackouts
        and not (incompatible.get(p.id, set()) & placed_ids)   # no clash on this shift
        and (p.max_shifts is None or worked[p.id] < p.max_shifts)
    ]
    if not eligible:
        return None

    # Fairness ranking - see the module docstring. `name` last makes the whole
    # ordering total, so the result is reproducible run to run.
    eligible.sort(key=lambda p: (worked[p.id], last_worked[p.id], p.name.lower()))
    return eligible[0]


def format_table(roster: Roster, people: list[Person],
                 shifts: list[ShiftType]) -> str:
    """Render a roster as the aligned monospace table shown in the app and exports.

    Columns are Date | Day | one per shift type, followed by a per-person shift
    summary and any notes the scheduler raised.
    """
    names = {p.id: p.name for p in people}
    shift_list = list(shifts)

    # Index assignments by (date, shift) so each cell is a single lookup.
    cells: dict[tuple[date, int], list[str]] = {}
    for a in roster.assignments:
        cells.setdefault((a.work_date, a.shift_type_id), []).append(
            names.get(a.person_id, f"#{a.person_id}"))

    days = sorted({a.work_date for a in roster.assignments}) or \
        date_range(roster.start_date, roster.end_date, set(range(7)))

    headers = ["Date", "Day"] + [s.label for s in shift_list]
    rows = [
        [d.strftime("%d %b %Y"), d.strftime("%a")] +
        [", ".join(sorted(cells.get((d, s.id), []))) or "-" for s in shift_list]
        for d in days
    ]

    # Column widths are the widest cell in each column, header included.
    widths = [max(len(headers[i]), *(len(r[i]) for r in rows)) if rows
              else len(headers[i]) for i in range(len(headers))]

    def line(cols: list[str]) -> str:
        """Pad one row's cells out to the computed column widths."""
        return "  ".join(c.ljust(widths[i]) for i, c in enumerate(cols)).rstrip()

    out = [line(headers), "  ".join("-" * w for w in widths)]
    out += [line(r) for r in rows]

    # Fairness summary: how many shifts each person actually ended up with.
    counts = roster.counts()
    if counts:
        out += ["", "Summary"]
        for pid, n in sorted(counts.items(),
                             key=lambda kv: (-kv[1], names.get(kv[0], ""))):
            out.append(f"  {names.get(pid, f'#{pid}')}: {n} shift"
                       f"{'s' if n != 1 else ''}")

    if roster.notes:
        out += ["", "Notes"]
        out += [f"  - {n}" for n in roster.notes]

    return "\n".join(out)
