/* JARVIS web — app shell cache. Network first, so an update reaches every
 * device on its next open; the cache only answers when offline. */
const CACHE = 'jarvis-web-v3';
const SHELL = ['./', 'index.html', 'manifest.webmanifest', 'icon.svg', 'icon-192.png'];
self.addEventListener('install', e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener('activate', e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', e => {
  const u = new URL(e.request.url);
  if (e.request.method !== 'GET' || u.origin !== location.origin) return;   // GitHub, Gemini: never cached
  if (u.pathname.endsWith('version.json')) return;                            // always the live version
  // no-cache: always ask the server (a 304 is cheap), so an update is seen at once
  e.respondWith(fetch(e.request, { cache: 'no-cache' }).then(r => { const c = r.clone(); caches.open(CACHE).then(k => k.put(e.request, c)); return r; })
                                .catch(() => caches.match(e.request).then(r => r || caches.match('index.html'))));
});
