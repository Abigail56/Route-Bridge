/* RouteBridge driver service worker: makes /driver load offline. API traffic is never cached (the app keeps its own
   encrypted offline data); only the app shell and hashed static assets are. */
const CACHE = 'rb-driver-shell-v2';

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(['/driver', '/manifest.webmanifest', '/driver-icon.svg', '/driver-icon-192.png']).catch(() => undefined)));
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)))).then(() => self.clients.claim()));
});

// ---- phone alerts: the server pushes {title, body, url} when a delivery is assigned ----
self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch { data = { body: event.data ? event.data.text() : '' }; }
  event.waitUntil(self.registration.showNotification(data.title || 'RouteBridge', {
    body: data.body || 'Open the app to see it.', icon: '/driver-icon-192.png', badge: '/driver-icon-192.png',
    tag: 'rb-assignment', renotify: true, data: { url: data.url || '/driver' },
  }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.url) || '/driver';
  event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windows) => {
    const open = windows.find((w) => new URL(w.url).pathname === target);
    return open ? open.focus() : self.clients.openWindow(target);
  }));
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin) return; // API calls go straight to the network
  const isShell = url.pathname === '/driver' || url.pathname === '/manifest.webmanifest' || url.pathname === '/driver-icon.svg';
  const isAsset = url.pathname.startsWith('/_next/static/');
  if (!isShell && !isAsset) return;
  // network-first for the shell (pick up new deployments), cache-first for immutable hashed assets
  event.respondWith(
    isAsset
      ? caches.match(request).then((hit) => hit || fetch(request).then((response) => { const copy = response.clone(); caches.open(CACHE).then((c) => c.put(request, copy)); return response; }))
      : fetch(request).then((response) => { const copy = response.clone(); caches.open(CACHE).then((c) => c.put(request, copy)); return response; }).catch(() => caches.match(request).then((hit) => hit || caches.match('/driver')))
  );
});
