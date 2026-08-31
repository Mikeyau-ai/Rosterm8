/**
 * Manual roster editing: swap, add or remove the people on any shift after a
 * roster has been built. Shared by the just-built result (New Roster) and an
 * opened saved roster.
 *
 * The scheduler's fill is deterministic and usually right, but the real world
 * throws late swaps at it - someone calls in sick, two people trade a day - and
 * going back to change availability and rebuilding would reshuffle everything
 * else. This lets the roster be nudged in place instead.
 */
import { el } from '../ui.js';
import { formatDate, toDays, weekdayOf } from '../scheduler.js';

/**
 * People who could be put on `date` without double-booking them or working
 * them through a blackout.
 *
 * Sorted by name. Someone whose standing weekday pattern doesn't cover the date
 * is still offered - a manual edit is a deliberate override - but the caller
 * flags them so it is a conscious choice, not a slip.
 */
export function candidatesFor(roster, people, date) {
  const busy = new Set(
    roster.assignments.filter((a) => a.date === date).map((a) => a.personId)
  );
  const n = toDays(date);
  return people
    .filter((p) => p.active && !busy.has(p.id))
    .filter((p) => !(p.blackouts || []).some(
      (b) => toDays(b.start) <= n && n <= toDays(b.end)
    ))
    .sort((a, b) => a.name.localeCompare(b.name));
}

/**
 * The day-by-day cards in edit mode: every shift row shows its people as
 * removable chips plus an "add" picker. `apply(nextAssignments)` is called with
 * a new assignments array on every change and is responsible for persisting it
 * and re-rendering.
 */
export function editableDayCards(roster, people, shifts, apply) {
  const nameOf = (id) => people.find((p) => p.id === id)?.name || '(removed)';
  const days = roster.days?.length
    ? [...roster.days].sort()
    : [...new Set(roster.assignments.map((a) => a.date))].sort();

  return days.map((day) => {
    const rows = shifts.map((shift) => {
      const here = roster.assignments.filter(
        (a) => a.date === day && a.shiftId === shift.id
      );
      const candidates = candidatesFor(roster, people, day);

      // One removable chip per person currently on this shift.
      const chips = here.map((a) => el('span', { className: 'edit-chip' }, [
        nameOf(a.personId),
        el('button', {
          type: 'button', className: 'edit-x', textContent: '×',
          'aria-label': `Remove ${nameOf(a.personId)} from ${shift.name} on ${day}`,
          onclick: () => apply(roster.assignments.filter((x) => x !== a)),
        }),
      ]));

      // A picker of everyone who could take a place on this shift.
      let adder = null;
      if (candidates.length) {
        const select = el('select', { className: 'edit-add' }, [
          el('option', {
            value: '',
            textContent: here.length < shift.headcount ? '+ add' : '+ add another',
          }),
          ...candidates.map((p) => el('option', {
            value: String(p.id),
            textContent: p.availableWeekdays.includes(weekdayOf(day))
              ? p.name
              : `${p.name} · usually off`,
          })),
        ]);
        select.addEventListener('change', () => {
          const id = Number(select.value);
          if (id) {
            apply([...roster.assignments, { date: day, shiftId: shift.id, personId: id }]);
          }
        });
        adder = select;
      }

      const short = here.length < shift.headcount;
      return el('div', { className: 'day-shift' }, [
        el('span', { className: 'sname', textContent: shift.name }),
        el('span', { className: short ? 'swho edit gap' : 'swho edit' }, [
          ...chips,
          adder,
          !chips.length && !adder
            ? el('span', { className: 'faint', textContent: 'nobody free' })
            : null,
        ]),
      ]);
    });

    return el('div', { className: 'day-card' }, [
      el('div', { className: 'day-date', textContent: formatDate(day) }),
      ...rows,
    ]);
  });
}
