/**
 * Saved screen: browse previously built rosters, and open one to review,
 * copy, share, or delete it. Follows the same list-then-detail pattern as
 * the People screen - there is no side-by-side layout on a phone.
 */
import { store } from '../store.js';
import { formatTable, counts, formatDate } from '../scheduler.js';
import { el, fill, toast, confirmDialog, copyText, emptyState } from '../ui.js';
import { show } from '../app.js';

// Id of the saved roster currently open, or null when showing the list.
let openId = null;

/** Entry point: render the list, or the opened roster, into `container`. */
export function render(container) {
  const rosters = store.rosters();
  if (rosters.length === 0) {
    openId = null;
    fill(container, [emptyState(
      'No saved rosters yet',
      'Build one on the Roster screen.',
      el('button', { className: 'btn btn-primary', textContent: 'Build a roster', onclick: () => show('roster') })
    )]);
    return;
  }

  const opened = openId != null ? rosters.find((r) => r.id === openId) : null;
  if (opened) {
    fill(container, renderOpen(opened, container));
  } else {
    openId = null;
    fill(container, renderList(rosters, container));
  }
}

/** Build the list of saved rosters, newest first. */
function renderList(rosters, container) {
  const items = rosters.map((r) => {
    const shiftsCount = r.assignments.length;
    return el('button', {
      type: 'button', className: 'item',
      onclick: () => { openId = r.id; render(container); },
    }, [
      el('div', { className: 'item-main' }, [
        el('div', { className: 'item-title', textContent: r.name }),
        el('div', {
          className: 'item-sub',
          textContent: `${formatDate(r.startDate, { withWeekday: false })} – ${formatDate(r.endDate, { withWeekday: false })} · ${shiftsCount} shift${shiftsCount === 1 ? '' : 's'} assigned`,
        }),
      ]),
    ]);
  });
  return [el('div', { className: 'list' }, items)];
}

/** Build the full day-by-day view of one saved roster, plus its actions. */
function renderOpen(roster, container) {
  const people = store.people();
  const shifts = store.shifts();
  const nodes = [];

  nodes.push(el('button', {
    className: 'btn btn-ghost', textContent: '← Back',
    onclick: () => { openId = null; render(container); },
  }));

  if (roster.notes.length > 0) {
    nodes.push(el('div', { className: 'notice bad' }, [
      el('strong', { textContent: `${roster.notes.length} thing${roster.notes.length === 1 ? '' : 's'} to check` }),
      el('ul', {}, roster.notes.map((n) => el('li', { textContent: n }))),
    ]));
  }

  nodes.push(...renderDayCards(roster, people, shifts));
  nodes.push(renderTally(roster, people));

  const actions = [
    el('button', {
      className: 'btn', textContent: 'Copy',
      onclick: () => copyText(formatTable(roster, people, shifts)),
    }),
  ];
  if (navigator.share) {
    actions.push(el('button', {
      className: 'btn', textContent: 'Share',
      onclick: async () => {
        try {
          await navigator.share({ title: roster.name, text: formatTable(roster, people, shifts) });
        } catch (e) {
          if (e && e.name === 'AbortError') return; // dismissing the sheet is not an error
        }
      },
    }));
  }
  actions.push(el('button', {
    className: 'btn btn-danger', textContent: 'Delete',
    onclick: async () => {
      const ok = await confirmDialog('Delete roster?', 'This cannot be undone.', 'Delete');
      if (!ok) return;
      store.deleteRoster(roster.id);
      openId = null;
      toast('Deleted');
      render(container);
    },
  }));
  nodes.push(el('div', { className: 'row' }, actions));

  return nodes;
}

/**
 * One `day-card` per date with an assignment, one `day-shift` row per shift.
 * A saved roster does not persist its weekday selection, so the day list is
 * derived from the assignments themselves (matching formatTable). A person
 * or shift deleted since the roster was saved falls back to "(removed)"
 * rather than crashing.
 */
function renderDayCards(roster, people, shifts) {
  const peopleById = new Map(people.map((p) => [p.id, p.name]));
  const shiftsById = new Map(shifts.map((s) => [s.id, s]));
  // Prefer the day list the scheduler recorded, so days where nothing could be
  // filled still appear. Rosters saved before that field existed fall back to
  // the dates that actually got someone assigned.
  const days = roster.days?.length
    ? [...roster.days].sort()
    : [...new Set(roster.assignments.map((a) => a.date))].sort();

  return days.map((day) => {
    const byShift = new Map();
    for (const a of roster.assignments) {
      if (a.date !== day) continue;
      if (!byShift.has(a.shiftId)) byShift.set(a.shiftId, []);
      byShift.get(a.shiftId).push(peopleById.get(a.personId) || '(removed)');
    }

    // Known shifts first, in their current fill order; any shift id no
    // longer in the organisation (deleted since saving) goes last.
    const knownIds = shifts.filter((s) => byShift.has(s.id)).map((s) => s.id);
    const extraIds = [...byShift.keys()].filter((id) => !shiftsById.has(id));
    const orderedIds = [...knownIds, ...extraIds];

    const rows = orderedIds.map((sid) => {
      const shift = shiftsById.get(sid);
      const names = byShift.get(sid);
      let whoText = names.join(', ');
      let gap = false;
      if (shift && names.length < shift.headcount) {
        whoText += ` (needs ${shift.headcount - names.length} more)`;
        gap = true;
      }
      return el('div', { className: 'day-shift' }, [
        el('span', { className: 'sname', textContent: shift ? shift.name : '(removed)' }),
        el('span', { className: gap ? 'swho gap' : 'swho', textContent: whoText }),
      ]);
    });

    return el('div', { className: 'day-card' }, [
      el('div', { className: 'day-date', textContent: formatDate(day) }),
      ...rows,
    ]);
  });
}

/** "Who's on how much": one chip per person, busiest first. */
function renderTally(roster, people) {
  const peopleById = new Map(people.map((p) => [p.id, p.name]));
  const entries = [...counts(roster).entries()]
    .map(([id, n]) => [peopleById.get(id) || '(removed)', n])
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));

  return el('div', { className: 'tally' }, entries.map(([name, n]) => (
    el('span', { className: 'chip' }, [`${name} `, el('b', { textContent: String(n) })])
  )));
}
