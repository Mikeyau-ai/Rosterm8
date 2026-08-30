# Rosterm8

A small web app for building staff rosters without writing lists out by hand and
shuffling people around who can't work certain days.

Add your people, tick the days each of them can work, note who's away and who
shouldn't be paired up, then press **Build roster**. Rosterm8 spreads the shifts
fairly, honours every constraint you gave it, and tells you plainly when it
couldn't fill something rather than quietly fudging it.

Built for a small church cafe's casual weekend roster, but nothing in it is
specific to that — it handles any set of named shifts on any days of the week.

**It runs entirely on your device.** No account, no server, no sign-in. Your
roster data never leaves the phone or laptop you typed it into.

## Using it

Open the site, tap **Add to Home Screen** (Safari: Share → Add to Home Screen;
Chrome: menu → Install app), and it behaves like an installed app — full screen,
its own icon, and it works with no signal.

The app has three sections:

- **Roster** — the rosters you've saved. This is what you open it to look at.
- **New Roster** — the calendar and the Build button.
- **Settings** — everything you set up once: People, Shifts, Opening hours,
  plus backup, AI assist, appearance and the home-screen shortcut.

1. **Name your organisation** — the cafe, the shop, the team. You can have more
   than one; the dropdown at the top switches between them.
2. **Settings → Shifts** — the blocks of work a day is made of, e.g. `Cafe 08:00–12:00,
   2 people needed`. They're filled in the order listed.
3. **Settings → People** — add everyone, tick the days each can work, add any away dates,
   and set any "never roster these two together" pairs.
4. **New Roster** — tap the dates you want on the calendar, press **Build**.
   Save it, and it appears under **Roster**. You can copy it or share it
   straight into a message.

### Opening days and hours

Set these once in **Settings → Opening hours**:

- **Open on** — the days you normally trade. Everything else is dimmed on the
  roster calendar, and an **All open days** shortcut appears. Dimmed, not
  blocked: you can still pick a closed day for a one-off, and it shows dashed
  so it's obvious it's an exception.
- **Opening hours** — used to fill in the times when you add a new shift, so
  the usual case needs no typing.

Every time field steps in 5-minute blocks rather than single minutes, which
makes the picker far quicker to thumb through on a phone.

### Picking dates

The calendar takes exact dates rather than a repeating rule, because real
rosters aren't a clean pattern — you're closed one weekend, and open for a
market on a Wednesday.

The bulk buttons under each month keep the ordinary case quick: open September,
tap **All open days**, and every trading day that month is selected. Then tap
any single date to switch it off. Tapping a bulk button again when every
matching date is already selected clears them, so it doubles as an undo.

### Repeating weekly

Tick **Repeat weekly** and the pattern you picked in the first week carries
forward — set it either as a number of weeks or as an end date, whichever suits;
the two stay in step.

It's recalculated each time rather than only added to, so dropping 12 weeks to 4
takes the later dates back off again. Unticking returns you to the first week.

## Backups matter

Everything is stored in this browser's local storage. That's what makes the app
private and free to run — but it also means **clearing your browsing data will
erase it**. Use **Settings → Backup → Export** every so often and keep the file in
Files, Drive or iCloud. **Restore from backup** puts it all back.

## The scheduler

`js/scheduler.js` is the part that matters, and it is deliberately boring:
given the same inputs it always produces the same roster. No AI, no randomness.

For each vacancy it ranks everyone who is eligible by

1. fewest shifts worked so far in this roster — spread the load
2. longest since they last worked — spread the days out
3. name — a stable tiebreak, so the result never changes between runs

and takes the top candidate. It works from the exact dates picked on the
calendar, and enforces weekly availability, away dates, "never together"
pairs, an optional per-person cap, and one shift per person per day. Anything it can't satisfy becomes a note on
the roster instead of a silent gap.

It was ported from the original Python version and produces byte-identical
output; `tests/scheduler.test.mjs` is the ported test suite that proves it.

```bash
node --test tests/scheduler.test.mjs
```

## The AI bit is optional

**Settings → AI assist** lets you paste in the kind of note you'd actually get
sent — *"Sarah can only do Saturdays"*, *"Tom's away 5–9 June"*, *"don't put
Rachel and Kate on together"* — and turns it into ticked days and away dates for
you to approve before anything is saved. Names it doesn't recognise are thrown
away.

It never decides who works when. That's always the scheduler.

Supported: Gemini, Anthropic and OpenAI. The key is stored on your device only.
Note that anyone who can use the device can read it out of the browser — fine
for a personal phone, not for a shared one. The app works completely without a
key; you just tick the days yourself.

## Running it locally

It's a static site with no build step. Any static server will do:

```bash
python dev-server.py
```

Then open `http://localhost:8123`. A plain `file://` open won't work — ES modules
need a real origin.

`dev-server.py` exists rather than `python -m http.server` because that sends no
cache headers, so browsers hold on to stale JavaScript after an edit and it looks
like your change did nothing. The service worker is also skipped on localhost for
the same reason — offline is verified against the deployed site.

## Layout

| Area | Files |
|------|-------|
| Shell | `index.html`, `css/app.css` |
| Boot + nav | `js/app.js` |
| Allocation | `js/scheduler.js` |
| Storage + backup | `js/store.js` |
| AI assist | `js/ai.js` |
| Shared widgets | `js/ui.js` |
| Home-screen install | `js/install.js` |
| Screens | `js/views/*.js` |
| Offline | `sw.js`, `manifest.webmanifest` |
| Branding | `make_icons.py` → `icons/` |
| Tests | `tests/scheduler.test.mjs` |

`legacy-desktop/` holds the original Windows CustomTkinter app this replaced. It
still runs, but it is no longer developed — the web app is the live version.

## Deploying

Hosted on GitHub Pages straight from the default branch. Push, and the site
updates; there is nothing to build and nothing to install.

The service worker serves the cached copy first and refreshes in the
background, so an installed copy picks up a change on the **second** open,
not the first. Add any new file to the `SHELL` list in `sw.js` so it is
available offline.
