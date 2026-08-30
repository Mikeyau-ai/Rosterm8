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

1. **Name your organisation** — the cafe, the shop, the team. You can have more
   than one; the dropdown at the top switches between them.
2. **Shifts** — the blocks of work a day is made of, e.g. `Cafe 08:00–12:00,
   2 people needed`. They're filled in the order listed.
3. **People** — add everyone, tick the days each can work, add any away dates,
   and set any "never roster these two together" pairs.
4. **Roster** — pick the dates and which weekdays to roster, press **Build**.
   Save it, copy it, or share it straight into a message.

## Backups matter

Everything is stored in this browser's local storage. That's what makes the app
private and free to run — but it also means **clearing your browsing data will
erase it**. Use **Settings → Export backup** every so often and keep the file in
Files, Drive or iCloud. **Restore from backup** puts it all back.

## The scheduler

`js/scheduler.js` is the part that matters, and it is deliberately boring:
given the same inputs it always produces the same roster. No AI, no randomness.

For each vacancy it ranks everyone who is eligible by

1. fewest shifts worked so far in this roster — spread the load
2. longest since they last worked — spread the days out
3. name — a stable tiebreak, so the result never changes between runs

and takes the top candidate. It enforces weekly availability, away dates,
"never together" pairs, an optional per-person cap, and one shift per person per
day. Anything it can't satisfy becomes a note on the roster instead of a silent
gap.

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
python -m http.server 8000
```

Then open `http://localhost:8000`. A plain `file://` open won't work — ES modules
and the service worker both need a real origin.

## Layout

| Area | Files |
|------|-------|
| Shell | `index.html`, `css/app.css` |
| Boot + nav | `js/app.js` |
| Allocation | `js/scheduler.js` |
| Storage + backup | `js/store.js` |
| AI assist | `js/ai.js` |
| Shared widgets | `js/ui.js` |
| Screens | `js/views/*.js` |
| Offline | `sw.js`, `manifest.webmanifest` |
| Branding | `make_icons.py` → `icons/` |
| Tests | `tests/scheduler.test.mjs` |

`legacy-desktop/` holds the original Windows CustomTkinter app this replaced. It
still runs, but it is no longer developed — the web app is the live version.

## Deploying

Hosted on GitHub Pages straight from the default branch. Push, and the site
updates; there is nothing to build and nothing to install.

When you change any file listed in `sw.js`, bump the `CACHE` constant at the top
of it — that's what tells already-installed copies to fetch the new version.
