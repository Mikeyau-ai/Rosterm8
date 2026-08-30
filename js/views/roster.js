/**
 * Roster screen: the app's home screen. Pick a date range and days of the
 * week, build a roster, then save/copy/share it. This is the single most
 * used screen, so the common weekend-cafe case (Sat+Sun, a fortnight out)
 * is the default and building must take as few taps as possible on a phone.
 */
import { store } from '../store.js';
import {
  buildRoster, dateRange, formatTable, counts, formatDate, toDays, fromDays,
} from '../scheduler.js';
import { parseAvailability, describe, AIError } from '../ai.js';
import {
  el, fill, toast, confirmDialog, weekdayPicker, copyText, emptyState,
} from '../ui.js';
import { show } from '../app.js';

// The most recently built roster, kept across re-renders (e.g. after Save)
// so the result isn't lost. `days` is the exact list of rostered dates used
// to build it, kept alongside since a saved roster does not store weekdays.
// Cleared whenever the current organisation changes.
let built = null;
let builtOrgId = null;

/** Today's date as "YYYY-MM-DD". */
function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

/** Entry point: render the build form, optional AI notes box, and any result. */
export function render(container) {
  const org = store.currentOrg();
  if (builtOrgId !== org.id) {
    built = null;
    builtOrgId = org.id;
  }

  const start = todayISO();
  const end = fromDays(toDays(start) + 13);

  const nameInput = el('input', {
    type: 'text', value: `Roster ${formatDate(start, { withWeekday: false })}`,
  });
  const startInput = el('input', { type: 'date', value: start });
  const endInput = el('input', { type: 'date', value: end });

  // Keep the suggested name in step with the start date, but stop the moment
  // the user types their own - a roster they named "Christmas" must not get
  // silently renamed when they nudge the dates.
  let nameIsAuto = true;
  nameInput.addEventListener('input', () => { nameIsAuto = false; });
  startInput.addEventListener('change', () => {
    if (nameIsAuto && startInput.value) {
      nameInput.value = `Roster ${formatDate(startInput.value, { withWeekday: false })}`;
    }
  });

  // The scheduler wants a Set of 0-6 weekday indices; default to the weekend,
  // since a small church cafe's weekend roster is the primary use case.
  let weekdaysState = [5, 6];
  const weekdaysWrap = el('div');
  /** Redraw the weekday chips from `weekdaysState` (needed since presets change it programmatically). */
  const renderWeekdayPicker = () => {
    fill(weekdaysWrap, weekdayPicker(weekdaysState, (sel) => { weekdaysState = sel; }));
  };
  renderWeekdayPicker();

  /** Build a preset button that sets `weekdaysState` to a fixed day list. */
  const preset = (label, days) => el('button', {
    type: 'button', className: 'btn btn-sm', textContent: label,
    onclick: () => { weekdaysState = days.slice(); renderWeekdayPicker(); },
  });
  const presets = el('div', { className: 'row-tight' }, [
    preset('Weekend', [5, 6]),
    preset('Weekdays', [0, 1, 2, 3, 4]),
    preset('Every day', [0, 1, 2, 3, 4, 5, 6]),
  ]);

  const activePeople = store.people().filter((p) => p.active);
  const shifts = store.shifts();
  const readiness = el('div', {
    className: 'faint',
    textContent: `${activePeople.length} people · ${shifts.length} shifts`,
  });

  const errDiv = el('div', { className: 'err' });
  const resultsBox = el('div');

  /** Redraw just the result section, without disturbing the form above it. */
  const renderResults = () => {
    fill(resultsBox, built ? buildResultView(container) : []);
  };

  /** Build the roster from the current form values and show the result. */
  const onBuild = () => {
    errDiv.textContent = '';
    if (!startInput.value || !endInput.value) {
      errDiv.textContent = 'Pick a start and end date.';
      return;
    }
    const weekdaysSet = new Set(weekdaysState);
    const roster = buildRoster({
      orgId: org.id,
      name: nameInput.value.trim() || `Roster ${formatDate(startInput.value, { withWeekday: false })}`,
      people: store.people(),
      shifts: store.shifts(),
      clashes: store.clashes(),
      start: startInput.value,
      end: endInput.value,
      weekdays: weekdaysSet,
    });
    built = { roster, days: dateRange(startInput.value, endInput.value, weekdaysSet) };
    renderResults();
  };

  // The build control is either the big primary button, or - if the org has
  // nothing to schedule yet - a pointer to the screen that fixes it. Either
  // way the scheduler is never invoked with nothing to work with.
  let buildControl;
  if (shifts.length === 0) {
    buildControl = emptyState(
      'No shifts yet',
      'Add at least one shift before building a roster.',
      el('button', {
        className: 'btn btn-primary', textContent: 'Add shifts', onclick: () => show('shifts'),
      })
    );
  } else if (activePeople.length === 0) {
    buildControl = emptyState(
      'No active people yet',
      'Add people before building a roster.',
      el('button', {
        className: 'btn btn-primary', textContent: 'Add people', onclick: () => show('people'),
      })
    );
  } else {
    buildControl = el('button', {
      className: 'btn btn-primary btn-lg btn-block', textContent: 'Build roster', onclick: onBuild,
    });
  }

  const formCard = el('div', { className: 'card' }, [
    el('div', {}, [el('label', { className: 'label', textContent: 'Roster name' }), nameInput]),
    el('div', { className: 'grid-2' }, [
      el('div', {}, [el('label', { className: 'label', textContent: 'Start' }), startInput]),
      el('div', {}, [el('label', { className: 'label', textContent: 'End' }), endInput]),
    ]),
    el('div', {}, [el('label', { className: 'label', textContent: 'Days to roster' }), weekdaysWrap, presets]),
    readiness,
    errDiv,
    buildControl,
  ]);

  renderResults();
  fill(container, [formCard, availabilityDetails(container), resultsBox]);
}

/** Build the collapsible "read availability from free text" section. */
function availabilityDetails(container) {
  const textarea = el('textarea', {
    rows: 4,
    placeholder: 'e.g. Sarah can only do Saturdays\nTom away 5-9 June\ndon\'t put Rachel and Kate on together',
  });
  const aiBtn = el('button', { className: 'btn', textContent: 'Read notes with AI' });
  const err = el('div', { className: 'err' });

  const provider = store.setting('aiProvider');
  const model = store.setting('aiModel');
  const apiKey = store.setting('aiKey');

  let noKeyNote = null;
  if (!apiKey) {
    aiBtn.disabled = true;
    noKeyNote = el('div', { className: 'muted', textContent: 'Add an API key in Settings to use this' });
  }

  aiBtn.addEventListener('click', async () => {
    err.textContent = '';
    aiBtn.disabled = true;
    aiBtn.textContent = 'Reading…';
    try {
      const people = store.people();
      const names = people.map((p) => p.name);
      const start = todayISO();
      const end = fromDays(toDays(start) + 13);
      const result = await parseAvailability({ text: textarea.value, names, start, end, provider, model, apiKey });
      const lines = describe(result);
      if (lines.length === 0) {
        toast('Nothing recognisable in those notes.');
        return;
      }
      const ok = await confirmDialog('Apply these changes?', lines.join('\n'), 'Apply');
      if (!ok) return;

      // Only now do we touch the store - everything above was read-only review.
      const byName = new Map(people.map((p) => [p.name.toLowerCase(), p]));
      let count = 0;
      for (const p of result.people) {
        const person = byName.get(p.name.toLowerCase());
        if (!person) continue;
        if (p.weekdays) {
          store.updatePerson(person.id, { availableWeekdays: p.weekdays });
          count++;
        }
        for (const b of p.blackouts || []) {
          store.addBlackout(person.id, b.start, b.end, b.reason);
          count++;
        }
      }
      for (const [a, b] of result.clashes) {
        const pa = byName.get(a.toLowerCase());
        const pb = byName.get(b.toLowerCase());
        if (pa && pb) {
          store.addClash(pa.id, pb.id);
          count++;
        }
      }
      toast(`${count} change${count === 1 ? '' : 's'} applied`);
      render(container);
    } catch (e) {
      err.textContent = e instanceof AIError ? e.message : 'Something went wrong reading those notes.';
    } finally {
      aiBtn.disabled = false;
      aiBtn.textContent = 'Read notes with AI';
    }
  });

  return el('details', {}, [
    el('summary', { textContent: 'Add availability from notes' }),
    el('div', { className: 'card' }, [textarea, noKeyNote, aiBtn, err]),
  ]);
}

/** Build the day-by-day result view, tally and action buttons for `built`. */
function buildResultView(container) {
  const { roster, days } = built;
  const people = store.people();
  const shifts = store.shifts();
  const nodes = [];

  // A shortfall must be impossible to miss, so it goes above the schedule.
  if (roster.notes.length > 0) {
    nodes.push(el('div', { className: 'notice bad' }, [
      el('strong', { textContent: `${roster.notes.length} thing${roster.notes.length === 1 ? '' : 's'} to check` }),
      el('ul', {}, roster.notes.map((n) => el('li', { textContent: n }))),
    ]));
  }

  nodes.push(...renderDayCards(roster, people, shifts, days));
  nodes.push(renderTally(roster, people));

  const actions = [
    el('button', {
      className: 'btn btn-primary', textContent: 'Save',
      onclick: () => {
        store.saveRoster(roster);
        toast('Saved');
        render(container);
      },
    }),
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
  nodes.push(el('div', { className: 'row' }, actions));

  return nodes;
}

/**
 * One `day-card` per rostered date, with one `day-shift` row per shift.
 * `days` and `shifts` come from the moment the roster was built, so every
 * shift on every day is represented even if it ended up with nobody on it.
 */
function renderDayCards(roster, people, shifts, days) {
  const peopleById = new Map(people.map((p) => [p.id, p.name]));

  return days.map((day) => {
    const rows = shifts.map((shift) => {
      const names = roster.assignments
        .filter((a) => a.date === day && a.shiftId === shift.id)
        .map((a) => peopleById.get(a.personId) || '(removed)');

      let whoText = names.join(', ');
      let gap = false;
      if (names.length === 0) {
        whoText = 'Nobody available';
        gap = true;
      } else if (names.length < shift.headcount) {
        whoText += ` (needs ${shift.headcount - names.length} more)`;
        gap = true;
      }

      return el('div', { className: 'day-shift' }, [
        el('span', { className: 'sname', textContent: shift.name }),
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
