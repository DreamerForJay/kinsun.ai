'use client';

import { useEffect } from 'react';

const PWA_CACHE_PREFIXES = ['elderly-care-shell-', 'elderly-care-public-assets-'];

async function removeDevelopmentServiceWorker(): Promise<void> {
  const registrations = await navigator.serviceWorker.getRegistrations();
  await Promise.all(registrations.map((registration) => registration.unregister()));

  if (!('caches' in window)) return;
  const cacheNames = await window.caches.keys();
  await Promise.all(
    cacheNames
      .filter((name) => PWA_CACHE_PREFIXES.some((prefix) => name.startsWith(prefix)))
      .map((name) => window.caches.delete(name)),
  );
}

export function ServiceWorkerRegistration() {
  useEffect(() => {
    if (!('serviceWorker' in navigator)) return;

    // A development worker can serve HTML from an older Next build and create
    // a reload loop when the referenced chunks no longer exist. Remove both
    // the worker and its historical caches locally; PWA registration is only
    // useful in a production build.
    if (process.env.NODE_ENV !== 'production') {
      void removeDevelopmentServiceWorker().catch(() => {
        console.error('[PWA] development service worker cleanup failed');
      });
      return;
    }

    void navigator.serviceWorker
      .register('/sw.js', { updateViaCache: 'none' })
      .then((registration) => registration.update())
      .catch(() => {
        console.error('[PWA] service worker registration failed');
      });
  }, []);

  return null;
}
