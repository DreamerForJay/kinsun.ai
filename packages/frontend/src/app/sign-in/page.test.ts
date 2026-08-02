import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  cookieGet: vi.fn(),
  clearBrowserStateRender: vi.fn(),
}));

vi.mock('next/headers', () => ({
  cookies: async () => ({ get: mocks.cookieGet }),
}));

vi.mock('@/components/ClearBrowserSessionState', () => ({
  ClearBrowserSessionState: () => {
    mocks.clearBrowserStateRender();
    return null;
  },
}));

import SignInPage from './page';

beforeEach(() => {
  mocks.cookieGet.mockReset();
  mocks.clearBrowserStateRender.mockReset();
});

describe('sign-in browser-state cleanup guard', () => {
  it('preserves browser state while an access-token cookie remains', async () => {
    mocks.cookieGet.mockReturnValue({ value: 'synthetic-access-token' });

    const page = await SignInPage({ searchParams: Promise.resolve({}) });
    renderToStaticMarkup(page);

    expect(mocks.cookieGet).toHaveBeenCalledWith('kinsun_access_token');
    expect(mocks.clearBrowserStateRender).not.toHaveBeenCalled();
  });

  it('clears stale browser state when no access-token cookie remains', async () => {
    mocks.cookieGet.mockReturnValue(undefined);

    const page = await SignInPage({ searchParams: Promise.resolve({}) });
    renderToStaticMarkup(page);

    expect(mocks.clearBrowserStateRender).toHaveBeenCalledTimes(1);
  });
});
