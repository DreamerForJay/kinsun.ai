'use client';

import { useEffect } from 'react';

export function ServiceWorkerRegistration() {
  useEffect(() => {
    if (!('serviceWorker' in navigator)) return;

    const hadController = navigator.serviceWorker.controller !== null;
    let reloading = false;
    const reloadAfterUpgrade = () => {
      if (!hadController || reloading) return;
      reloading = true;
      window.location.reload();
    };

    navigator.serviceWorker.addEventListener('controllerchange', reloadAfterUpgrade);
    void navigator.serviceWorker
      .register('/sw.js', { updateViaCache: 'none' })
      .then((registration) => registration.update())
      .catch((err) => {
        console.error('[PWA] service worker registration failed', err);
      });

    return () => {
      navigator.serviceWorker.removeEventListener('controllerchange', reloadAfterUpgrade);
    };
  }, []);

  return null;
}
