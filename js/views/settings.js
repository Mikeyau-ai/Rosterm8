/**
 * Settings screen: organisation management, backup/restore, AI assist config,
 * theme, and the destructive "delete everything" escape hatch.
 */
import { store } from '../store.js';
import { PROVIDERS } from '../ai.js';
import { el, fill, toast, promptText, confirmDialog, downloadText, weekdayPicker } from '../ui.js';
import { show, refreshOrgs } from '../app.js';

const THEME_KEY = 'rosterm8.theme';

/**
 * Apply a saved theme preference to the document immediately.
 * Run once at module load (below) so the choice survives a page reload, not
 * only after the user revisits Settings and clicks a button.
 */
function applyTheme(value) {
  if (value) document.documentElement.dataset.theme = value;
  else delete document.documentElement.dataset.theme;
}

// Apply whatever was saved last time, right away at module load.
applyTheme(localStorage.getItem(THEME_KEY) || '');

/** Entry point: render every settings section into `container`. */
export function render(container) {
  fill(container, [
    el('h2', { textContent: 'Settings' }),
    renderOrgCard(),
    renderBackupCard(container),
    renderAICard(),
    renderThemeCard(),
    renderAboutCard(),
  ]);
}

/** Section: rename or delete the current organisation. */
function renderOrgCard() {
  const org = store.currentOrg();
  if (!org) {
    return el('div', { className: 'card' }, [
      el('h3', { textContent: 'This organisation' }),
      el('div', { className: 'muted', textContent: 'No organisation selected yet.' }),
    ]);
  }

  const nameInput = el('input', { type: 'text', value: org.name });
  const saveBtn = el('button', {
    className: 'btn btn-sm', textContent: 'Save',
    onclick: () => {
      const value = nameInput.value.trim();
      if (!value) return;
      store.renameOrg(org.id, value);
      refreshOrgs();
      toast('Renamed');
    },
  });
  const deleteBtn = el('button', {
    className: 'btn btn-danger', textContent: 'Delete organisation',
    onclick: async () => {
      const ok = await confirmDialog(
        'Delete organisation',
        `This deletes "${org.name}" and all of its people, shifts and saved rosters. This cannot be undone.`
      );
      if (!ok) return;
      store.deleteOrg(org.id);
      refreshOrgs();
      show('roster');
      toast('Organisation deleted');
    },
  });

  return el('div', { className: 'card' }, [
    el('h3', { textContent: 'This organisation' }),
    el('div', { className: 'row-tight' }, [nameInput, saveBtn]),
    renderOpeningHours(org),
    deleteBtn,
  ]);
}

/**
 * Opening days and hours for the current organisation.
 *
 * The days drive the calendar on the Roster screen - anything outside them is
 * dimmed, and an "All open days" shortcut appears. The hours are used to
 * pre-fill the times when a new shift is added, so the common case needs no
 * typing.
 */
function renderOpeningHours(org) {
  const openTime = el('input', { type: 'time', value: org.openTime || '' });
  const closeTime = el('input', { type: 'time', value: org.closeTime || '' });

  /** Persist whichever hour field changed. */
  const saveHours = () => {
    store.updateOrg(org.id, { openTime: openTime.value, closeTime: closeTime.value });
  };
  openTime.addEventListener('change', saveHours);
  closeTime.addEventListener('change', saveHours);

  const daysWrap = el('div');
  fill(daysWrap, weekdayPicker(store.openDays(), (days) => {
    store.updateOrg(org.id, { openDays: days });
  }));

  return el('div', {}, [
    el('label', { className: 'label', textContent: 'Open on' }),
    daysWrap,
    el('div', {
      className: 'faint',
      textContent: 'Days you are closed are dimmed on the roster calendar. You can still pick them for a one-off.',
      style: 'margin-top:.35rem',
    }),
    el('label', { className: 'label', textContent: 'Opening hours', style: 'margin-top:.8rem' }),
    el('div', { className: 'grid-2' }, [
      el('div', {}, [el('label', { className: 'faint', textContent: 'Opens' }), openTime]),
      el('div', {}, [el('label', { className: 'faint', textContent: 'Closes' }), closeTime]),
    ]),
    el('div', {
      className: 'faint',
      textContent: 'Used to fill in the times when you add a new shift.',
      style: 'margin-top:.35rem',
    }),
  ]);
}

/** Section: export/import the whole database as a JSON backup file. */
function renderBackupCard(container) {
  const importErr = el('div', { className: 'err' });

  const fileInput = el('input', {
    type: 'file', accept: 'application/json,.json', hidden: true,
    onchange: async () => {
      const file = fileInput.files[0];
      if (!file) return;
      const ok = await confirmDialog(
        'Restore from backup',
        'This replaces everything currently on this device with the contents of this backup file. This cannot be undone.',
        'Restore'
      );
      fileInput.value = '';
      if (!ok) return;
      try {
        const text = await file.text();
        store.importJSON(text);
        importErr.textContent = '';
        refreshOrgs();
        toast('Backup restored');
        show('roster');
      } catch (err) {
        importErr.textContent = err.message;
      }
    },
  });

  const exportBtn = el('button', {
    className: 'btn btn-primary btn-block', textContent: 'Export backup',
    onclick: () => {
      const date = new Date().toISOString().slice(0, 10);
      downloadText(`rosterm8-backup-${date}.json`, store.exportJSON(), 'application/json');
      toast('Backup downloaded');
    },
  });
  const importBtn = el('button', {
    className: 'btn btn-block', textContent: 'Restore from backup',
    onclick: () => fileInput.click(),
  });

  return el('div', { className: 'card' }, [
    el('h3', { textContent: 'Backup' }),
    el('div', {
      className: 'notice',
      textContent: 'Your data lives only in this browser, on this device. Clearing browsing data, ' +
        'reinstalling the browser, or switching phones would erase it. Export a backup occasionally, ' +
        'and keep the file somewhere safe (Files, email to yourself, Drive).',
    }),
    exportBtn,
    importBtn,
    fileInput,
    importErr,
  ]);
}

/** Section: AI provider/model/key used to parse availability notes. */
function renderAICard() {
  const provider = store.setting('aiProvider') || 'gemini';
  const spec = PROVIDERS[provider] || PROVIDERS.gemini;

  const providerSelect = el('select', {}, Object.entries(PROVIDERS).map(([key, p]) =>
    el('option', { value: key, textContent: p.label, selected: key === provider })
  ));

  const modelInput = el('input', {
    type: 'text', value: store.setting('aiModel') || '', placeholder: spec.defaultModel,
    onblur: () => store.setSetting('aiModel', modelInput.value.trim()),
  });

  const keyInput = el('input', {
    type: 'password', value: store.setting('aiKey') || '',
    onblur: () => store.setSetting('aiKey', keyInput.value.trim()),
  });
  const showHideBtn = el('button', {
    className: 'btn btn-sm', textContent: 'Show',
    onclick: () => {
      const hidden = keyInput.type === 'password';
      keyInput.type = hidden ? 'text' : 'password';
      showHideBtn.textContent = hidden ? 'Hide' : 'Show';
    },
  });

  const keyLink = el('a', {
    href: spec.keyUrl, target: '_blank', rel: 'noopener', textContent: 'Get a key',
  });

  providerSelect.addEventListener('change', () => {
    store.setSetting('aiProvider', providerSelect.value);
    const newSpec = PROVIDERS[providerSelect.value];
    modelInput.placeholder = newSpec.defaultModel;
    keyLink.href = newSpec.keyUrl;
  });

  return el('div', { className: 'card' }, [
    el('h3', { textContent: 'AI assist' }),
    el('p', { className: 'muted' }, [
      'AI is only used to turn free-text availability notes into structured days and away-dates. ' +
      'It never decides who works when - the roster itself is worked out by a fixed set of rules ' +
      'that always give the same answer.',
    ]),
    el('div', {}, [el('label', { className: 'label', textContent: 'Provider' }), providerSelect]),
    el('div', {}, [el('label', { className: 'label', textContent: 'Model' }), modelInput]),
    el('div', {}, [
      el('label', { className: 'label', textContent: 'API key' }),
      el('div', { className: 'row-tight' }, [keyInput, showHideBtn]),
    ]),
    keyLink,
    el('div', {
      className: 'faint',
      textContent: 'The key is stored on this device only, and is readable by anyone who can use this ' +
        'device. Fine for personal use - avoid it on a shared phone.',
    }),
  ]);
}

/** Section: light/dark/system theme control. */
function renderThemeCard() {
  const current = localStorage.getItem(THEME_KEY) || '';
  const options = [
    { value: '', label: 'System' },
    { value: 'light', label: 'Light' },
    { value: 'dark', label: 'Dark' },
  ];

  const buttons = options.map((opt) => el('button', {
    type: 'button',
    className: `btn btn-sm${opt.value === current ? ' btn-primary' : ''}`,
    textContent: opt.label,
    onclick: () => {
      localStorage.setItem(THEME_KEY, opt.value);
      applyTheme(opt.value);
      for (const [i, other] of options.entries()) {
        buttons[i].className = `btn btn-sm${other.value === opt.value ? ' btn-primary' : ''}`;
      }
    },
  }));

  return el('div', { className: 'card' }, [
    el('h3', { textContent: 'Theme' }),
    el('div', { className: 'row' }, buttons),
  ]);
}

/** Section: app identity and the full data wipe. */
function renderAboutCard() {
  const deleteAllBtn = el('button', {
    className: 'btn btn-danger btn-block', textContent: 'Delete all data',
    onclick: async () => {
      const ok = await confirmDialog(
        'Delete all data',
        'This permanently deletes every organisation, person, shift and saved roster on this device. ' +
          'There is no undo. Make sure you have a backup if you might want any of this again.',
        'Delete everything'
      );
      if (!ok) return;
      store.reset();
      refreshOrgs();
      show('roster');
      toast('All data deleted');
    },
  });

  return el('div', { className: 'card' }, [
    el('h3', { textContent: 'About' }),
    el('div', { textContent: 'Rosterm8' }),
    el('div', { className: 'muted', textContent: 'Everything stays on this device.' }),
    deleteAllBtn,
  ]);
}
