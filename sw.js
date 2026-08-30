/**
 * Service worker: makes Rosterm8 open with no connection.
 *
 * Strategy is cache-first for the app shell, because the shell is small, fully
 * static and versioned by CACHE below — a roster built in a cafe basement with
 * no signal must still work. Bumping CACHE on deploy is what ships an update:
 * the new worker precaches the new files and deletes every older cache.
 *
 * Only same-origin GETs are touched. The AI provider calls in js/ai.js are
 * cross-origin and must always go to the network, never to a cache.
 */

const CACHE = 'rosterm8-v1';

/** Everything needed to boot the app with no network. */
const SHELL = [
  './',
  './index.html',
  './manifest.webmanifest',
  './css/app.css',
  './js/app.js',
  './js/ui.js',
  './js/store.js',
  './js/scheduler.js',
  './js/ai.js',
  './js/views/roster.js',
  './js/views/people.js',
  './js/views/shifts.js',
  './js/views/saved.js',
  './js/views/settings.js',
  './icons/icon-192.png',
  './icons/icon-512.png',
];

self.addEventListener('install', (event) => {
  // addAll is atomic: if any file 404s the whole install fails, which is what
  // we want rather than a half-cached, subtly broken app.
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;   // let AI calls hit the network

  // Stale-while-revalidate: answer instantly from cache (so the app opens with
  // no signal), but always re-fetch in the background and store the new copy,
  // so the next open has the latest. Plain cache-first would mean a forgotten
  // CACHE bump silently pins every installed copy to an old version forever -
  // the wrong failure mode for an app nobody is watching over.
  event.respondWith(
    caches.open(CACHE).then(async (cache) => {
      const hit = await cache.match(request);

      const network = fetch(request)
        .then((response) => {
          if (response.ok && response.type === 'basic') cache.put(request, response.clone());
          return response;
        })
        .catch(() => null);

      if (hit) return hit;

      const fresh = await network;
      if (fresh) return fresh;

      // Offline with nothing cached: a navigation still gets the shell, which
      // is enough for this single-page app to render.
      if (request.mode === 'navigate') {
        return (await cache.match('./index.html')) || Response.error();
      }
      return Response.error();
    })
  );
});
