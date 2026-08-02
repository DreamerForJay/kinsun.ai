// Minimal public-asset service worker for the elder-care PWA.
//
// Never cache navigations or BFF responses: `/` changes by authentication
// state, so a cache-first HTML shell can both stay stale after a deployment
// and show the wrong session's page shape on a shared tablet. Voice and data
// access already require the network; only identity-free public assets belong
// in this cache.
const CACHE_NAME = 'elderly-care-public-assets-v2';
const PUBLIC_ASSETS = ['/manifest.json', '/mascot.png'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll(PUBLIC_ASSETS))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  if (event.request.mode === 'navigate' || url.pathname.startsWith('/backend/')) return;
  if (!PUBLIC_ASSETS.includes(url.pathname)) return;

  event.respondWith(
    caches.match(event.request).then((cached) => cached ?? fetch(event.request)),
  );
});
