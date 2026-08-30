/**
 * Small DOM helpers shared by every view.
 *
 * Deliberately not a framework: this app has five screens and a few dialogs, so
 * a handful of functions over plain DOM beats pulling in a dependency that has
 * to be cached, updated and understood.
 */
import { weekdayOf } from './scheduler.js';

/** Weekday labels, Monday-first, matching the scheduler's 0-6 indices. */
export const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

/**
 * Create an element.
 * `attrs` sets properties (className, textContent, onclick, ...); anything
 * containing a dash or starting "aria"/"data" is set as an attribute instead.
 */
export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k.startsWith('aria') || k.startsWith('data') || k.includes('-')) {
      node.setAttribute(k, v);
    } else {
      node[k] = v;
    }
  }
  for (const child of [].concat(children)) {
    if (child == null || child === false) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}

/** Replace an element's contents with the given children. */
export function fill(node, children) {
  node.replaceChildren(...[].concat(children).filter((c) => c != null && c !== false));
  return node;
}

/** Show a brief confirmation message at the bottom of the screen. */
let toastTimer = null;
export function toast(message) {
  const node = document.getElementById('toast');
  node.textContent = message;
  node.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove('show'), 2400);
}

/**
 * Open the shared <dialog> with caller-supplied content.
 * `render(close)` builds the body and calls close(result) to resolve.
 * Returns a promise of whatever close() was given (null if dismissed).
 */
export function dialog(render) {
  const modal = document.getElementById('modal');
  return new Promise((resolve) => {
    let settled = false;
    const close = (result = null) => {
      if (settled) return;
      settled = true;
      modal.close();
      modal.replaceChildren();
      resolve(result);
    };
    // Covers Esc and backdrop dismissal, which bypass our own buttons.
    modal.addEventListener('close', () => close(null), { once: true });

    const body = el('div', { className: 'modal-body' }, render(close));
    fill(modal, body);
    modal.showModal();

    const firstField = modal.querySelector('input, textarea, select');
    if (firstField) firstField.focus();
  });
}

/** Ask for a single line of text. Resolves to the trimmed string, or null. */
export function promptText(title, label, initial = '') {
  return dialog((close) => {
    const input = el('input', { type: 'text', value: initial });
    const submit = () => {
      const value = input.value.trim();
      if (value) close(value);
    };
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') submit(); });
    return [
      el('h2', { textContent: title }),
      el('div', {}, [el('label', { className: 'label', textContent: label }), input]),
      el('div', { className: 'modal-actions' }, [
        el('button', { className: 'btn', textContent: 'Cancel', onclick: () => close(null) }),
        el('button', { className: 'btn btn-primary', textContent: 'Save', onclick: submit }),
      ]),
    ];
  });
}

/** Ask a yes/no question. Resolves true only if confirmed. */
export function confirmDialog(title, message, confirmLabel = 'Delete') {
  return dialog((close) => [
    el('h2', { textContent: title }),
    el('p', { className: 'muted', textContent: message }),
    el('div', { className: 'modal-actions' }, [
      el('button', { className: 'btn', textContent: 'Cancel', onclick: () => close(false) }),
      el('button', {
        className: 'btn btn-danger', textContent: confirmLabel,
        onclick: () => close(true),
      }),
    ]),
  ]);
}

/**
 * Ask for a date range plus an optional reason, for adding an away period.
 * Resolves to { start, end, reason } or null.
 */
export function promptDateRange(title) {
  return dialog((close) => {
    const today = new Date().toISOString().slice(0, 10);
    const start = el('input', { type: 'date', value: today });
    const end = el('input', { type: 'date', value: today });
    const reason = el('input', { type: 'text', placeholder: 'Holiday, course, ...' });
    const err = el('div', { className: 'err' });

    const submit = () => {
      if (!start.value) { err.textContent = 'Pick a start date.'; return; }
      // A single-day absence is the common case, so an empty end means "same day".
      const to = end.value || start.value;
      close({ start: start.value, end: to, reason: reason.value.trim() });
    };

    return [
      el('h2', { textContent: title }),
      el('div', { className: 'grid-2' }, [
        el('div', {}, [el('label', { className: 'label', textContent: 'From' }), start]),
        el('div', {}, [el('label', { className: 'label', textContent: 'To' }), end]),
      ]),
      el('div', {}, [el('label', { className: 'label', textContent: 'Reason (optional)' }), reason]),
      err,
      el('div', { className: 'modal-actions' }, [
        el('button', { className: 'btn', textContent: 'Cancel', onclick: () => close(null) }),
        el('button', { className: 'btn btn-primary', textContent: 'Add', onclick: submit }),
      ]),
    ];
  });
}

/**
 * A row of seven Mon-Sun toggle chips.
 * `selected` is an array of 0-6; onChange receives the updated sorted array.
 */
export function weekdayPicker(selected, onChange) {
  const chosen = new Set(selected);
  const wrap = el('div', { className: 'days' });

  DAY_LABELS.forEach((label, i) => {
    const chip = el('button', {
      type: 'button', className: 'day-chip', textContent: label,
      'aria-pressed': chosen.has(i) ? 'true' : 'false',
      'aria-label': label,
    });
    chip.addEventListener('click', () => {
      if (chosen.has(i)) chosen.delete(i); else chosen.add(i);
      chip.setAttribute('aria-pressed', chosen.has(i) ? 'true' : 'false');
      onChange([...chosen].sort((a, b) => a - b));
    });
    wrap.append(chip);
  });
  return wrap;
}

/** Month names for the calendar header. */
const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
                     'August', 'September', 'October', 'November', 'December'];

/**
 * A tappable month calendar for choosing exactly which dates to roster.
 *
 * Rosters in the real world are not a clean weekday pattern - a cafe skips the
 * weekend it's closed and adds the odd Christmas market - so the dates are
 * picked individually rather than derived from a rule. The per-month bulk
 * buttons keep the common case ("every weekend in September") down to one tap.
 *
 * `selected` is a Set of "YYYY-MM-DD" strings, mutated in place; `onChange` is
 * called after every change with that Set, so the caller can update its count.
 */
export function calendarPicker(selected, onChange) {
  const wrap = el('div', { className: 'cal' });

  // The month on show. Starts on whatever the user already picked, so
  // re-opening a part-built roster lands where they left off.
  const first = [...selected].sort()[0] || new Date().toISOString().slice(0, 10);
  let [year, month] = first.split('-').map(Number);   // month is 1-12 here

  /** Toggle one date and tell the caller. */
  const toggle = (iso) => {
    if (selected.has(iso)) selected.delete(iso); else selected.add(iso);
    onChange(selected);
  };

  /** Every date in the displayed month falling on one of `weekdays` (Mon=0). */
  const monthDatesFor = (weekdays) => {
    const out = [];
    const total = new Date(Date.UTC(year, month, 0)).getUTCDate();
    for (let d = 1; d <= total; d++) {
      const iso = `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
      if (weekdays.includes(weekdayOf(iso))) out.push(iso);
    }
    return out;
  };

  /** Add every matching date in this month, or remove them if all are already on. */
  const bulk = (weekdays) => {
    const dates = monthDatesFor(weekdays);
    const allOn = dates.every((d) => selected.has(d));
    for (const d of dates) {
      if (allOn) selected.delete(d); else selected.add(d);
    }
    onChange(selected);
    draw();
  };

  /** Step the displayed month by `delta` months. */
  const shiftMonth = (delta) => {
    month += delta;
    if (month < 1) { month = 12; year -= 1; }
    if (month > 12) { month = 1; year += 1; }
    draw();
  };

  /** Redraw the whole calendar for the current month. */
  function draw() {
    const todayISO = new Date().toISOString().slice(0, 10);
    const daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
    const firstISO = `${year}-${String(month).padStart(2, '0')}-01`;
    const leading = weekdayOf(firstISO);          // blank cells before the 1st

    const header = el('div', { className: 'cal-head' }, [
      el('button', {
        type: 'button', className: 'btn btn-sm', textContent: '‹',
        'aria-label': 'Previous month', onclick: () => shiftMonth(-1),
      }),
      el('div', { className: 'cal-month', textContent: `${MONTH_NAMES[month - 1]} ${year}` }),
      el('button', {
        type: 'button', className: 'btn btn-sm', textContent: '›',
        'aria-label': 'Next month', onclick: () => shiftMonth(1),
      }),
    ]);

    const grid = el('div', { className: 'cal-grid' });
    // Two letters, not one: "T" and "S" appear twice each, so single initials
    // make Tue/Thu and Sat/Sun indistinguishable at a glance.
    for (const label of DAY_LABELS) {
      grid.append(el('div', { className: 'cal-dow', textContent: label.slice(0, 2) }));
    }
    for (let i = 0; i < leading; i++) {
      grid.append(el('div', { className: 'cal-blank' }));
    }
    for (let d = 1; d <= daysInMonth; d++) {
      const iso = `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
      const cell = el('button', {
        type: 'button',
        className: `cal-day${iso === todayISO ? ' is-today' : ''}`,
        textContent: String(d),
        'aria-pressed': selected.has(iso) ? 'true' : 'false',
        'aria-label': iso,
      });
      cell.addEventListener('click', () => {
        toggle(iso);
        cell.setAttribute('aria-pressed', selected.has(iso) ? 'true' : 'false');
      });
      grid.append(cell);
    }

    const bulkRow = el('div', { className: 'row-tight cal-bulk' }, [
      el('button', { type: 'button', className: 'btn btn-sm', textContent: 'Saturdays',
                     onclick: () => bulk([5]) }),
      el('button', { type: 'button', className: 'btn btn-sm', textContent: 'Sundays',
                     onclick: () => bulk([6]) }),
      el('button', { type: 'button', className: 'btn btn-sm', textContent: 'Weekends',
                     onclick: () => bulk([5, 6]) }),
      el('button', { type: 'button', className: 'btn btn-sm', textContent: 'Weekdays',
                     onclick: () => bulk([0, 1, 2, 3, 4]) }),
    ]);

    fill(wrap, [header, grid, bulkRow]);
  }

  draw();
  return wrap;
}

/** Copy text to the clipboard, falling back for browsers without the async API. */
export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast('Copied');
  } catch {
    // Safari refuses clipboard writes outside a user gesture in some contexts;
    // the textarea trick still works there.
    const ta = el('textarea', { value: text });
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.append(ta);
    ta.select();
    try {
      document.execCommand('copy');
      toast('Copied');
    } catch {
      toast('Could not copy — select the text and copy manually');
    }
    ta.remove();
  }
}

/**
 * Offer a text file for download.
 * Used by Export; on iOS this opens the share sheet, which is the sane way to
 * get a backup into Files or Drive.
 */
export function downloadText(filename, text, type = 'text/plain') {
  const blob = new Blob([text], { type: `${type};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const link = el('a', { href: url, download: filename });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** A standard empty-state block. */
export function emptyState(title, detail, action) {
  return el('div', { className: 'empty' }, [
    el('strong', { textContent: title }),
    el('div', { className: 'muted', textContent: detail }),
    action ? el('div', { style: 'margin-top:.9rem' }, action) : null,
  ]);
}
