/* RouteBridge driver service worker: makes /driver load offline. API traffic is never cached (the app keeps its own
   encrypted offline data); only the app shell and hashed static assets are. */
const CACHE = 'rb-driver-shell-v1';

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(['/driver', '/manifest.webmanifest', '/driver-icon.svg']).catch(() => undefined)));
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)))).then(() => self.clients.claim()));
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
