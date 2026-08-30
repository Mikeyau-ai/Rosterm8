/**
 * Rosterm8 bootstrap: loads saved data, wires the nav and organisation
 * switcher, and hands control to whichever view is showing.
 *
 * Views are plain modules exporting `render(container)`. Switching view simply
 * re-renders; there is no virtual DOM and no client-side router beyond the hash,
 * which is enough for five screens and keeps the back button working.
 */
import { store } from './store.js';
import { el, fill, promptText, toast } from './ui.js';

import * as rosterView from './views/roster.js';
import * as peopleView from './views/people.js';
import * as shiftsView from './views/shifts.js';
import * as savedView from './views/saved.js';
import * as settingsView from './views/settings.js';

const VIEWS = {
  roster: rosterView,
  people: peopleView,
  shifts: shiftsView,
  saved: savedView,
  settings: settingsView,
};

const NEW_ORG = '__new__';

let current = 'roster';

/** Render the active view into <main>, or prompt for an organisation first. */
export function render() {
  const container = document.getElementById('view');

  // Every screen except Settings needs an organisation to act on.
  if (!store.currentOrg() && current !== 'settings') {
    fill(container, welcome());
    return;
  }
  VIEWS[current].render(container);
  container.scrollTop = 0;
}

/** First-run screen: there is nothing to show until a workplace exists. */
function welcome() {
  const create = async () => {
    const name = await promptText('New organisation', 'What do you call this workplace?');
    if (!name) return;
    store.addOrg(name);
    seedDefaults();
    refreshOrgs();
    show('shifts');
    toast(`${name} created — set up its shifts`);
  };

  return el('div', { className: 'card' }, [
    el('h2', { textContent: 'Welcome to Rosterm8' }),
    el('p', { className: 'muted' }, [
      'Build a fair roster in seconds: add your people, say which days each of them ' +
      'can work, and let Rosterm8 do the shuffling. Everything stays on this device.',
    ]),
    el('p', { className: 'muted', textContent: 'Start by naming the place you roster for — a cafe, a shop, a team.' }),
    el('button', {
      className: 'btn btn-primary btn-lg btn-block',
      textContent: 'Create an organisation', onclick: create,
    }),
  ]);
}

/**
 * Give a brand-new organisation one weekend shift to start from.
 * An empty Shifts screen is a dead end; a sensible default means the user can
 * go straight to adding people and press Build.
 */
function seedDefaults() {
  store.addShift({ name: 'Cafe', start: '08:00', end: '12:00', headcount: 2 });
}

/** Switch the visible view and update the tab bar. */
export function show(name) {
  if (!VIEWS[name]) name = 'roster';
  current = name;
  for (const tab of document.querySelectorAll('.tab')) {
    const active = tab.dataset.view === name;
    tab.setAttribute('aria-current', active ? 'page' : 'false');
  }
  if (location.hash !== `#${name}`) {
    history.replaceState(null, '', `#${name}`);
  }
  render();
}

/** Rebuild the organisation dropdown from the store. */
export function refreshOrgs() {
  const select = document.getElementById('org-select');
  const orgs = store.orgs();
  const currentId = store.data.currentOrgId;

  fill(select, [
    ...orgs.map((o) => el('option', {
      value: String(o.id), textContent: o.name, selected: o.id === currentId,
    })),
    el('option', { value: NEW_ORG, textContent: '+ New organisation…' }),
  ]);
  select.hidden = orgs.length === 0;
}

/** Handle a change in the organisation dropdown. */
async function onOrgChange(event) {
  const value = event.target.value;
  if (value === NEW_ORG) {
    const name = await promptText('New organisation', 'What do you call this workplace?');
    refreshOrgs();                       // revert the select if they cancelled
    if (!name) return;
    store.addOrg(name);
    seedDefaults();
    refreshOrgs();
    show('shifts');
    toast(`${name} created — set up its shifts`);
    return;
  }
  store.setCurrentOrg(Number(value));
  render();
}

/** Register the service worker so the app opens with no connection. */
function registerWorker() {
  if (!('serviceWorker' in navigator)) return;

  // Not during local development: the worker serves the previous version from
  // its cache on first load, so an edit appears not to have taken effect. That
  // is the right behaviour for an installed app and the wrong one at a code
  // editor. Offline is verified against the deployed site instead.
  if (['localhost', '127.0.0.1', '::1'].includes(location.hostname)) return;

  // Registration failure is not fatal - the app still works online - so this
  // must never surface an error to the user.
  navigator.serviceWorker.register('sw.js').catch(() => {});
}

/** Wire everything up and show the first screen. */
function init() {
  store.load();
  refreshOrgs();

  for (const tab of document.querySelectorAll('.tab')) {
    tab.addEventListener('click', () => show(tab.dataset.view));
  }
  document.getElementById('org-select').addEventListener('change', onOrgChange);
  window.addEventListener('hashchange', () => show(location.hash.slice(1)));

  show(location.hash.slice(1) || 'roster');
  registerWorker();
}

init();
