"""Plain dataclasses passed between the database, the scheduler and the GUI.

These are deliberately dumb value objects: the database module builds them from
rows and the scheduler consumes them, so neither has to know about the other's
representation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Organization:
    """A workplace that owns its own staff, shift types and rosters."""
    id: int
    name: str


@dataclass
class ShiftType:
    """One named shift an organization runs, e.g. 'Late 14:00-22:00, needs 3'."""
    id: int
    org_id: int
    name: str
    start_time: str          # "HH:MM", free text - display only, never parsed
    end_time: str            # "HH:MM"
    headcount: int           # how many people this shift needs
    sort_order: int          # display/allocation order within a day

    @property
    def label(self) -> str:
        """Human label used in tables and exports."""
        if self.start_time and self.end_time:
            return f"{self.name} ({self.start_time}-{self.end_time})"
        return self.name


@dataclass
class Person:
    """A staff member belonging to exactly one organization."""
    id: int
    org_id: int
    name: str
    active: bool = True
    notes: str = ""

    #: Weekday indices (0=Mon .. 6=Sun) this person can normally work.
    available_weekdays: set[int] = field(default_factory=lambda: set(range(7)))
    #: Inclusive (start, end) date ranges this person cannot work at all.
    blackouts: list[tuple[date, date]] = field(default_factory=list)
    #: Optional cap on shifts across a single roster; None means no cap.
    max_shifts: int | None = None

    def can_work(self, day: date) -> bool:
        """True if this person's standing availability allows working ``day``."""
        if not self.active:
            return False
        if day.weekday() not in self.available_weekdays:
            return False
        return not any(start <= day <= end for start, end in self.blackouts)


@dataclass
class Assignment:
    """One person placed on one shift on one date."""
    work_date: date
    shift_type_id: int
    person_id: int


@dataclass
class Roster:
    """A generated roster: its assignments plus anything the scheduler flagged."""
    org_id: int
    name: str
    start_date: date
    end_date: date
    assignments: list[Assignment] = field(default_factory=list)
    #: Human-readable problems, e.g. "Tue 3 Jun - Late: only 1 of 2 filled".
    notes: list[str] = field(default_factory=list)

    def counts(self) -> dict[int, int]:
        """Shifts worked per person id, for the fairness summary."""
        out: dict[int, int] = {}
        for a in self.assignments:
            out[a.person_id] = out.get(a.person_id, 0) + 1
        return out
