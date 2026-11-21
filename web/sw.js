/* MAYK web — app shell cache. Network first, so an update reaches every
 * device on its next open; the cache only answers when offline. */
const BUILD = new URL(self.location.href).searchParams.get('v') || 'development';
const PREFIX = 'mayk-web:' + self.registration.scope + ':';
const CACHE = PREFIX + BUILD;
const SCRIPTS = ['reactor', 'chess', 'devkit', 'app', 'dev-common', 'dev-phone',
                 'dev-tablet', 'dev-tv', 'dev-projector', 'dev-watch'];
const suffix = BUILD === 'development' ? '' : '?v=' + BUILD;
const SHELL = ['./', 'index.html', 'manifest.webmanifest', 'icon.svg', 'icon-192.png',
               'icon-512.png', ...SCRIPTS.map(name => name + '.js' + suffix)];
const urls = new Set(SHELL.map(path => new URL(path, self.registration.scope).href));
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(
    keys.filter(key => key.startsWith(PREFIX) && key !== CACHE).map(key => caches.delete(key))
  )).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET' || !request.url.startsWith(self.registration.scope)) return;
  const navigation = request.mode === 'navigate';
  if (!navigation && !urls.has(request.url)) return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    try {
      const response = await fetch(request, { cache: 'no-cache' });
      if (response.ok || response.status < 500) return response;
      return await cache.match(navigation ? 'index.html' : request) || response;
    } catch (error) {
      const saved = await cache.match(navigation ? 'index.html' : request);
      if (saved) return saved;
      throw error;
    }
  })());
});

// Notifications sent by the user's computer while this page is closed
// (core/webpush.py): a reminder, a photo from guard mode, a finished report.
self.addEventListener('push', e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch { d = { body: e.data ? e.data.text() : '' }; }
  e.waitUntil(self.registration.showNotification(d.title || 'MAYK', {
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
