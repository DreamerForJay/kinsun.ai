// @vitest-environment jsdom

import { cleanup, render, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ServiceWorkerRegistration } from './ServiceWorkerRegistration';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe('ServiceWorkerRegistration', () => {
  it('bypasses the HTTP cache when checking for an updated worker', async () => {
    vi.stubEnv('NODE_ENV', 'production');
    const update = vi.fn().mockResolvedValue(undefined);
    const register = vi.fn().mockResolvedValue({ update });

    Object.defineProperty(navigator, 'serviceWorker', {
      configurable: true,
      value: {
        register,
      },
    });

    render(createElement(ServiceWorkerRegistration));

    await waitFor(() => expect(update).toHaveBeenCalledTimes(1));
    expect(register).toHaveBeenCalledWith('/sw.js', { updateViaCache: 'none' });
  });

  it('removes workers and PWA caches instead of registering in development', async () => {
    vi.stubEnv('NODE_ENV', 'development');
    const unregister = vi.fn().mockResolvedValue(true);
    const register = vi.fn();
    const deleteCache = vi.fn().mockResolvedValue(true);

    Object.defineProperty(navigator, 'serviceWorker', {
      configurable: true,
      value: {
        getRegistrations: vi.fn().mockResolvedValue([{ unregister }]),
        register,
      },
    });
    vi.stubGlobal('caches', {
      keys: vi
        .fn()
        .mockResolvedValue(['elderly-care-shell-v1', 'elderly-care-public-assets-v2', 'other']),
      delete: deleteCache,
    });

    render(createElement(ServiceWorkerRegistration));

    await waitFor(() => expect(unregister).toHaveBeenCalledTimes(1));
    expect(register).not.toHaveBeenCalled();
    expect(deleteCache).toHaveBeenCalledWith('elderly-care-shell-v1');
    expect(deleteCache).toHaveBeenCalledWith('elderly-care-public-assets-v2');
    expect(deleteCache).not.toHaveBeenCalledWith('other');
  });
});
