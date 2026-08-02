// @vitest-environment jsdom

import { cleanup, render, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ServiceWorkerRegistration } from './ServiceWorkerRegistration';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('ServiceWorkerRegistration', () => {
  it('bypasses the HTTP cache when checking for an updated worker', async () => {
    const update = vi.fn().mockResolvedValue(undefined);
    const register = vi.fn().mockResolvedValue({ update });
    const addEventListener = vi.fn();
    const removeEventListener = vi.fn();

    Object.defineProperty(navigator, 'serviceWorker', {
      configurable: true,
      value: {
        controller: null,
        register,
        addEventListener,
        removeEventListener,
      },
    });

    const view = render(createElement(ServiceWorkerRegistration));

    await waitFor(() => expect(update).toHaveBeenCalledTimes(1));
    expect(register).toHaveBeenCalledWith('/sw.js', { updateViaCache: 'none' });
    expect(addEventListener).toHaveBeenCalledWith('controllerchange', expect.any(Function));

    view.unmount();
    expect(removeEventListener).toHaveBeenCalledWith('controllerchange', expect.any(Function));
  });
});
