/* Mayk web — app shell cache. Network first, so an update reaches every
 * device on its next open; the cache only answers when offline. */
const CACHE = 'jarvis-web-v5';
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

// Notifications sent by the user's computer while this page is closed
// (core/webpush.py): a reminder, a photo from guard mode, a finished report.
self.addEventListener('push', e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch { d = { body: e.data ? e.data.text() : '' }; }
  e.waitUntil(self.registration.showNotification(d.title || 'Mayk', {
    body: d.body || '', tag: d.tag || 'jarvis', renotify: true, icon: 'icon-192.png', badge: 'icon-192.png',
    vibrate: d.tag === 'alarm' ? [500, 200, 500, 200, 500] : [200, 100, 200], data: { url: './' } }));
});
self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
    for (const c of list) if ('focus' in c) return c.focus();
    return self.clients.openWindow('./');
  }));
});
