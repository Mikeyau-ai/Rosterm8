/**
 * On-device storage for Rosterm8.
 *
 * Everything lives in one JSON blob in localStorage. There is no server and no
 * account: the roster never leaves the device it was made on. A roster for a
 * dozen people over a few months is a few kilobytes, so a single blob is both
 * simpler and more robust than IndexedDB here - and it makes Export/Import a
 * one-liner, which is the real backup story.
 *
 * The data is organised in two layers: an **organisation** owns everything, and
 * people, shifts, clash rules and saved rosters all belong to exactly one
 * organisation. Switching organisation swaps the entire working set.
 */

const KEY = 'rosterm8.v1';

/** Shape of a brand-new, empty database. */
function emptyData() {
  return {
    version: 1,
    orgs: [],
    currentOrgId: null,
    shifts: [],
    people: [],
    clashes: [],
    rosters: [],
    settings: { aiProvider: 'gemini', aiModel: '', aiKey: '' },
  };
}

/** Monotonic-ish id generator; unique within this device, which is all we need. */
let idSeed = Date.now();
function newId() {
  idSeed += 1;
  return idSeed;
}

export const store = {
  data: emptyData(),

  /**
   * Load from localStorage, tolerating absent, corrupt or older data.
   * A parse failure must never leave the user staring at a broken app, so we
   * fall back to empty rather than throwing.
   */
  load() {
    try {
      const raw = localStorage.getItem(KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        this.data = { ...emptyData(), ...parsed };
        this.data.settings = { ...emptyData().settings, ...(parsed.settings || {}) };
      }
    } catch (err) {
      console.warn('Could not read saved data; starting fresh.', err);
      this.data = emptyData();
    }
    // Keep ids climbing above anything already stored, so a reload cannot
    // reissue an id that is still in use.
    const all = [...this.data.orgs, ...this.data.people, ...this.data.shifts, ...this.data.rosters];
    for (const item of all) if (item?.id >= idSeed) idSeed = item.id + 1;
    return this.data;
  },

  /**
   * Persist to localStorage. Returns false if the write failed (private mode,
   * quota, storage disabled) so the caller can warn instead of losing data
   * silently.
   */
  save() {
    try {
      localStorage.setItem(KEY, JSON.stringify(this.data));
      return true;
    } catch (err) {
      console.error('Could not save.', err);
      return false;
    }
  },

  // ---------------------------------------------------------- organisations --
  /** Every organisation, alphabetically. */
  orgs() {
    return [...this.data.orgs].sort((a, b) => a.name.localeCompare(b.name));
  },

  /** The organisation currently being worked on, or null if there are none. */
  currentOrg() {
    return this.data.orgs.find((o) => o.id === this.data.currentOrgId) || null;
  },

  /** Switch the working organisation. */
  setCurrentOrg(id) {
    this.data.currentOrgId = id;
    this.save();
  },

  /** Create an organisation, select it, and return it. */
  addOrg(name) {
    const org = { id: newId(), name: name.trim() };
    this.data.orgs.push(org);
    this.data.currentOrgId = org.id;
    this.save();
    return org;
  },

  /** Rename an organisation in place. */
  renameOrg(id, name) {
    const org = this.data.orgs.find((o) => o.id === id);
    if (org) org.name = name.trim();
    this.save();
  },

  /** Delete an organisation and everything inside it. */
  deleteOrg(id) {
    this.data.orgs = this.data.orgs.filter((o) => o.id !== id);
    this.data.people = this.data.people.filter((p) => p.orgId !== id);
    this.data.shifts = this.data.shifts.filter((s) => s.orgId !== id);
    this.data.clashes = this.data.clashes.filter((c) => c.orgId !== id);
    this.data.rosters = this.data.rosters.filter((r) => r.orgId !== id);
    if (this.data.currentOrgId === id) {
      this.data.currentOrgId = this.data.orgs[0]?.id ?? null;
    }
    this.save();
  },

  // ----------------------------------------------------------------- shifts --
  /** The current organisation's shifts, in the order the scheduler fills them. */
  shifts() {
    const org = this.data.currentOrgId;
    return this.data.shifts
      .filter((s) => s.orgId === org)
      .sort((a, b) => a.order - b.order || a.id - b.id);
  },

  /** Add a shift to the current organisation and return it. */
  addShift({ name = 'Day', start = '', end = '', headcount = 1 } = {}) {
    const shift = {
      id: newId(), orgId: this.data.currentOrgId,
      name, start, end, headcount,
      order: this.shifts().length,
    };
    this.data.shifts.push(shift);
    this.save();
    return shift;
  },

  /** Apply a patch to one shift. */
  updateShift(id, patch) {
    const shift = this.data.shifts.find((s) => s.id === id);
    if (shift) Object.assign(shift, patch);
    this.save();
  },

  /** Remove a shift. */
  deleteShift(id) {
    this.data.shifts = this.data.shifts.filter((s) => s.id !== id);
    this.shifts().forEach((s, i) => { s.order = i; });   // close the gap
    this.save();
  },

  /** Swap a shift with its neighbour, changing the fill order. */
  moveShift(id, delta) {
    const list = this.shifts();
    const i = list.findIndex((s) => s.id === id);
    const j = i + delta;
    if (i < 0 || j < 0 || j >= list.length) return;
    [list[i].order, list[j].order] = [list[j].order, list[i].order];
    this.save();
  },

  // ----------------------------------------------------------------- people --
  /** The current organisation's people, alphabetically. */
  people() {
    return this.data.people
      .filter((p) => p.orgId === this.data.currentOrgId)
      .sort((a, b) => a.name.localeCompare(b.name));
  },

  /** Add a person, available every day by default, and return them. */
  addPerson(name) {
    const person = {
      id: newId(), orgId: this.data.currentOrgId,
      name: name.trim(), active: true,
      availableWeekdays: [0, 1, 2, 3, 4, 5, 6],
      blackouts: [], maxShifts: null, notes: '',
    };
    this.data.people.push(person);
    this.save();
    return person;
  },

  /** Apply a patch to one person. */
  updatePerson(id, patch) {
    const person = this.data.people.find((p) => p.id === id);
    if (person) Object.assign(person, patch);
    this.save();
  },

  /** Remove a person and any clash rules that referenced them. */
  deletePerson(id) {
    this.data.people = this.data.people.filter((p) => p.id !== id);
    this.data.clashes = this.data.clashes.filter((c) => c.a !== id && c.b !== id);
    this.save();
  },

  /** Mark a person unavailable across an inclusive date range. */
  addBlackout(personId, start, end, reason = '') {
    const person = this.data.people.find((p) => p.id === personId);
    if (!person) return;
    if (end < start) [start, end] = [end, start];
    person.blackouts.push({ start, end, reason });
    person.blackouts.sort((x, y) => x.start.localeCompare(y.start));
    this.save();
  },

  /** Remove one blackout range by its position in the person's list. */
  deleteBlackout(personId, index) {
    const person = this.data.people.find((p) => p.id === personId);
    if (person) person.blackouts.splice(index, 1);
    this.save();
  },

  // ---------------------------------------------------------------- clashes --
  /** Person-id pairs in the current organisation that must not share a shift. */
  clashes() {
    return this.data.clashes
      .filter((c) => c.orgId === this.data.currentOrgId)
      .map((c) => [c.a, c.b]);
  },

  /** Record a clash. Pairs are stored unordered so they cannot be duplicated. */
  addClash(a, b) {
    if (a === b) return;
    const [lo, hi] = a < b ? [a, b] : [b, a];
    const exists = this.data.clashes.some(
      (c) => c.orgId === this.data.currentOrgId && c.a === lo && c.b === hi
    );
    if (!exists) this.data.clashes.push({ orgId: this.data.currentOrgId, a: lo, b: hi });
    this.save();
  },

  /** Remove a clash, whichever order the pair is given in. */
  deleteClash(a, b) {
    const [lo, hi] = a < b ? [a, b] : [b, a];
    this.data.clashes = this.data.clashes.filter(
      (c) => !(c.orgId === this.data.currentOrgId && c.a === lo && c.b === hi)
    );
    this.save();
  },

  // ---------------------------------------------------------------- rosters --
  /** Saved rosters for the current organisation, newest first. */
  rosters() {
    return this.data.rosters
      .filter((r) => r.orgId === this.data.currentOrgId)
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  },

  /** Persist a generated roster and return it with its new id. */
  saveRoster(roster) {
    const saved = { ...roster, id: newId(), createdAt: new Date().toISOString() };
    this.data.rosters.push(saved);
    this.save();
    return saved;
  },

  /** Delete a saved roster. */
  deleteRoster(id) {
    this.data.rosters = this.data.rosters.filter((r) => r.id !== id);
    this.save();
  },

  // --------------------------------------------------------------- settings --
  /** Read a setting. */
  setting(key) {
    return this.data.settings[key];
  },

  /** Write a setting. */
  setSetting(key, value) {
    this.data.settings[key] = value;
    this.save();
  },

  // ------------------------------------------------------- backup / restore --
  /**
   * The whole database as a formatted JSON string, for the Export button.
   * This is the backup: browser storage can be cleared by the browser itself,
   * so an occasional export to Files/Drive is the only real safety net.
   */
  exportJSON() {
    return JSON.stringify(this.data, null, 2);
  },

  /**
   * Replace everything with a previously exported backup.
   * Throws with a readable message if the file is not a Rosterm8 export, so the
   * caller can show it verbatim rather than inventing its own wording.
   */
  importJSON(text) {
    let parsed;
    try {
      parsed = JSON.parse(text);
    } catch {
      throw new Error("That file isn't valid JSON - pick a Rosterm8 backup file.");
    }
    if (!parsed || !Array.isArray(parsed.orgs) || !Array.isArray(parsed.people)) {
      throw new Error("That doesn't look like a Rosterm8 backup.");
    }
    this.data = { ...emptyData(), ...parsed };
    this.data.settings = { ...emptyData().settings, ...(parsed.settings || {}) };
    if (!this.save()) throw new Error('Restored, but saving to this device failed.');
    this.load();
  },

  /** Wipe everything on this device. Used by Settings > Delete all data. */
  reset() {
    this.data = emptyData();
    this.save();
  },
};
