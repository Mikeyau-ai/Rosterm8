/**
 * People screen: manage the roster of staff who can be scheduled.
 *
 * Two states are rendered into the same container: a list of everyone in the
 * current organisation, and (when a person is selected) a full-page editor for
 * that one person. There is no side-by-side layout - this is a phone app, and
 * a list-then-detail push is the natural pattern here.
 */
import { store } from '../store.js';
import { formatDate } from '../scheduler.js';
import {
  el, fill, toast, promptText, confirmDialog, promptDateRange, weekdayPicker,
} from '../ui.js';

// Id of the person currently open in the editor, or null when showing the list.
let editingId = null;

/** Entry point: render the list or the editor into `container`. */
export function render(container) {
  if (editingId != null && store.people().some((p) => p.id === editingId)) {
    fill(container, renderEditor(editingId, container));
  } else {
    editingId = null;
    fill(container, renderList(container));
  }
}

/** Build the "who can I work?" summary shown under each person's name. */
function availabilitySummary(person) {
  const days = person.availableWeekdays || [];
  let text;
  if (days.length === 7) text = 'Every day';
  else if (days.length === 0) text = 'No days ticked';
  else {
    const labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    text = [...days].sort((a, b) => a - b).map((d) => labels[d]).join(', ');
  }
  const away = person.blackouts?.length || 0;
  if (away > 0) text += ` · ${away} away`;
  return text;
}

/** Build the list view: header, add button, and one row per person. */
function renderList(container) {
  const addBtn = el('button', {
    className: 'btn btn-primary btn-sm', textContent: '+ Add',
    onclick: async () => {
      const name = await promptText('New person', "What's their name?");
      if (!name) return;
      const person = store.addPerson(name);
      editingId = person.id;
      render(container);
    },
  });

  const header = el('div', { className: 'spread' }, [
    el('h2', { textContent: 'People' }),
    addBtn,
  ]);

  const people = store.people();
  if (people.length === 0) {
    return [
      header,
      el('div', { className: 'card' }, [
        el('div', { textContent: 'No people yet' }),
        el('div', {
          className: 'muted',
          textContent: 'Add the people you roster, then tick the days each of them can work.',
        }),
      ]),
    ];
  }

  const list = el('div', { className: 'list' }, people.map((p) => {
    const item = el('button', {
      type: 'button',
      className: `item${p.active ? '' : ' inactive'}`,
      onclick: () => { editingId = p.id; render(container); },
    }, [
      el('div', { className: 'item-main' }, [
        el('div', { className: 'item-title', textContent: p.name }),
        el('div', { className: 'item-sub', textContent: availabilitySummary(p) }),
      ]),
    ]);
    return item;
  }));

  return [header, list];
}

/** Build the full editor for one person. */
function renderEditor(id, container) {
  const person = store.people().find((p) => p.id === id);
  const back = () => { editingId = null; render(container); };

  const backBtn = el('button', { className: 'btn btn-sm', textContent: '← Back', onclick: back });
  const header = el('div', { className: 'row-tight' }, [backBtn]);

  const nameCard = renderNameCard(person);
  const availCard = renderAvailabilityCard(person, container);
  const maxCard = renderMaxShiftsCard(person);
  const awayCard = renderAwayCard(person, container);
  const clashCard = renderClashCard(person, container);
  const deleteBtn = el('button', {
    className: 'btn btn-danger btn-block', textContent: 'Delete person',
    onclick: async () => {
      const ok = await confirmDialog('Delete person', `Remove ${person.name}? This cannot be undone.`);
      if (!ok) return;
      store.deletePerson(person.id);
      toast('Person deleted');
      back();
    },
  });

  // Everything already saves as you go, so Save is really "I'm done here" -
  // but it still commits the text fields first, so a value typed and never
  // blurred is kept, and it refuses to leave on a bad max-shifts value rather
  // than dropping it silently.
  const saveBtn = el('button', {
    className: 'btn btn-primary btn-block btn-lg', textContent: 'Save',
    onclick: () => {
      nameCard.commit();
      if (!maxCard.commit()) return;
      toast(`${store.people().find((p) => p.id === id)?.name || 'Person'} saved`);
      back();
    },
  });

  return [
    header, nameCard.node, availCard, maxCard.node, awayCard, clashCard,
    saveBtn, deleteBtn,
  ];
}

/**
 * Card: name text field and the active/inactive toggle.
 *
 * Returns `{ node, commit }`. Fields still save on blur, but Save calls
 * `commit()` too so a value typed and never blurred is not lost.
 */
function renderNameCard(person) {
  /** Save the typed name, falling back to the existing one if it's blank. */
  const commit = () => {
    const value = nameInput.value.trim();
    if (value) store.updatePerson(person.id, { name: value });
    else nameInput.value = person.name;
    return true;
  };

  const nameInput = el('input', {
    type: 'text', value: person.name,
    onblur: commit,
  });

  const activeCheckbox = el('input', {
    type: 'checkbox', checked: person.active,
    onchange: () => store.updatePerson(person.id, { active: activeCheckbox.checked }),
  });

  const node = el('div', { className: 'card' }, [
    el('div', {}, [el('label', { className: 'label', textContent: 'Name' }), nameInput]),
    el('label', { className: 'row-tight' }, [
      activeCheckbox,
      el('span', { textContent: 'Active' }),
    ]),
    el('div', {
      className: 'faint',
      textContent: 'Inactive people are kept on the list but are never rostered.',
    }),
  ]);

  return { node, commit };
}

/** Card: the weekday picker for standing availability. */
function renderAvailabilityCard(person, container) {
  const picker = weekdayPicker(person.availableWeekdays, (days) => {
    store.updatePerson(person.id, { availableWeekdays: days });
  });
  return el('div', { className: 'card' }, [
    el('label', { className: 'label', textContent: 'Available on' }),
    picker,
  ]);
}

/**
 * Card: max shifts per roster, validated as blank or a positive integer.
 *
 * Returns `{ node, commit }`; `commit()` is false when the value is invalid,
 * so Save can keep the user on the screen instead of discarding what they typed.
 */
function renderMaxShiftsCard(person) {
  const input = el('input', {
    type: 'number', min: '1', step: '1',
    value: person.maxShifts == null ? '' : String(person.maxShifts),
  });
  const err = el('div', { className: 'err' });

  /** Validate and save the cap. Returns false (and shows why) if unusable. */
  const commit = () => {
    const raw = input.value.trim();
    if (raw === '') {
      err.textContent = '';
      store.updatePerson(person.id, { maxShifts: null });
      return true;
    }
    const n = Number(raw);
    if (!Number.isInteger(n) || n <= 0) {
      err.textContent = 'Enter a positive whole number, or leave blank for no cap.';
      return false;
    }
    err.textContent = '';
    store.updatePerson(person.id, { maxShifts: n });
    return true;
  };

  input.addEventListener('blur', commit);

  const node = el('div', { className: 'card' }, [
    el('label', { className: 'label', textContent: 'Max shifts per roster' }),
    input,
    err,
  ]);

  return { node, commit };
}

/** Card: away-date (blackout) ranges, with add/remove. */
function renderAwayCard(person, container) {
  const rows = (person.blackouts || []).map((b, i) => {
    const span = b.start === b.end
      ? formatDate(b.start, { withWeekday: false })
      : `${formatDate(b.start, { withWeekday: false })} – ${formatDate(b.end, { withWeekday: false })}`;
    return el('div', { className: 'spread' }, [
      el('div', {}, [
        el('div', { textContent: span }),
        b.reason ? el('div', { className: 'muted', textContent: b.reason }) : null,
      ]),
      el('button', {
        className: 'btn btn-sm', textContent: 'Remove',
        onclick: () => {
          store.deleteBlackout(person.id, i);
          render(container);
        },
      }),
    ]);
  });

  const addBtn = el('button', {
    className: 'btn btn-sm', textContent: '+ Add away dates',
    onclick: async () => {
      const result = await promptDateRange('Away dates');
      if (!result) return;
      store.addBlackout(person.id, result.start, result.end, result.reason);
      render(container);
    },
  });

  return el('div', { className: 'card' }, [
    el('label', { className: 'label', textContent: 'Away dates' }),
    rows.length ? el('div', { className: 'list' }, rows) : el('div', { className: 'muted', textContent: 'None recorded.' }),
    addBtn,
  ]);
}

/** Card: "never with" clash rules against other people. */
function renderClashCard(person, container) {
  const others = store.people().filter((p) => p.id !== person.id);
  const partnerIds = store.clashes()
    .filter(([a, b]) => a === person.id || b === person.id)
    .map(([a, b]) => (a === person.id ? b : a));

  const rows = partnerIds.map((pid) => {
    const other = others.find((p) => p.id === pid);
    return el('div', { className: 'spread' }, [
      el('div', { textContent: other ? other.name : `#${pid}` }),
      el('button', {
        className: 'btn btn-sm', textContent: 'Remove',
        onclick: () => {
          store.deleteClash(person.id, pid);
          render(container);
        },
      }),
    ]);
  });

  const available = others.filter((p) => !partnerIds.includes(p.id));
  let addRow = null;
  if (available.length > 0) {
    const select = el('select', {}, available.map((p) => el('option', { value: String(p.id), textContent: p.name })));
    addRow = el('div', { className: 'row-tight' }, [
      select,
      el('button', {
        className: 'btn btn-sm', textContent: 'Add',
        onclick: () => {
          store.addClash(person.id, Number(select.value));
          render(container);
        },
      }),
    ]);
  }

  return el('div', { className: 'card' }, [
    el('label', { className: 'label', textContent: 'Never with' }),
    rows.length ? el('div', { className: 'list' }, rows) : el('div', { className: 'muted', textContent: 'No clash rules.' }),
    addRow,
  ]);
}
