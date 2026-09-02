/**
 * Turn a pasted list of names into people to add, one per line.
 *
 * This is the keyless, offline counterpart to `js/ai.js`: no model, no network,
 * just a small deterministic parser for the format you'd type yourself -
 *
 *   Sarah - Sat, Sun
 *   Tom - weekdays
 *   Rachel
 *   Kate - every day
 *
 * A line is a name on its own, or a name and a day spec separated by a dash
 * (-, en dash, em dash), a colon, or a tab. Everything before the separator is
 * the name; everything after is parsed into weekday indices (Mon=0), matching
 * the scheduler's convention.
 *
 * It does not dedupe or check names against existing people - the caller does
 * that against the real org, the same way `ai.js` validates against real names.
 */

/** Day words to weekday indices (Monday = 0), matching the scheduler. */
const DAY_WORDS = {
  mon: 0, monday: 0,
  tue: 1, tues: 1, tuesday: 1,
  wed: 2, weds: 2, wednesday: 2,
  thu: 3, thur: 3, thurs: 3, thursday: 3,
  fri: 4, friday: 4,
  sat: 5, saturday: 5,
  sun: 6, sunday: 6,
};

/** Group words that expand to several days. */
const DAY_GROUPS = {
  weekday: [0, 1, 2, 3, 4], weekdays: [0, 1, 2, 3, 4],
  weekend: [5, 6], weekends: [5, 6],
  everyday: [0, 1, 2, 3, 4, 5, 6], daily: [0, 1, 2, 3, 4, 5, 6],
  all: [0, 1, 2, 3, 4, 5, 6], any: [0, 1, 2, 3, 4, 5, 6],
};

/**
 * Parse a day spec ("Sat, Sun", "weekdays", "every day", "none") into a sorted
 * array of weekday indices.
 *
 * Returns `null` when the spec has words but none were recognised - that is
 * "I tried to say something and it didn't land", which should send the person
 * to the day-picker, not silently give them no days. An explicit "none" returns
 * `[]`, meaning the user really does want them ticked nowhere yet.
 */
function parseDaySpec(spec) {
  // Collapse the common two-word spellings so they match a single group word.
  const normalised = spec.toLowerCase()
    .replace(/every\s*day/g, 'everyday')
    .replace(/week\s*days?/g, 'weekdays')
    .replace(/week\s*ends?/g, 'weekends');
  const tokens = normalised.split(/[\s,/&]+/).filter(Boolean);
  if (tokens.length === 0) return null;
  if (tokens.length === 1 && tokens[0] === 'none') return [];

  const days = new Set();
  let recognised = false;
  for (const token of tokens) {
    if (token in DAY_GROUPS) {
      DAY_GROUPS[token].forEach((d) => days.add(d));
      recognised = true;
    } else if (token in DAY_WORDS) {
      days.add(DAY_WORDS[token]);
      recognised = true;
    }
  }
  if (!recognised) return null;
  return [...days].sort((a, b) => a - b);
}

/**
 * Parse pasted text into `[{ name, weekdays }]`, in the order given.
 *
 * `weekdays` is a sorted array of indices, or `null` when the line named no
 * days (or named only unrecognised ones). Blank lines are skipped. Lines with
 * an empty name (a leading separator) are skipped too.
 */
export function parsePeopleList(text) {
  const people = [];
  for (const raw of String(text).split('\n')) {
    // Tolerate a pasted bullet list: drop a leading -, *, • and its space.
    const line = raw.trim().replace(/^[-–—*•]\s+/, '');
    if (!line) continue;

    // A dash must have whitespace on both sides so hyphenated names ("Mary-Jane")
    // are left whole; a colon only needs a space after it; a tab always splits.
    const sep = line.match(/\s+[-–—]\s+|\s*:\s+|\t/);
    let name = line;
    let weekdays = null;
    if (sep) {
      name = line.slice(0, sep.index).trim();
      weekdays = parseDaySpec(line.slice(sep.index + sep[0].length).trim());
    }
    if (!name) continue;

    people.push({ name, weekdays });
  }
  return people;
}
