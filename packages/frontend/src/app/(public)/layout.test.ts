import { createElement, type ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  cookieGet: vi.fn(),
  shellProps: vi.fn(),
}));

vi.mock('next/headers', () => ({
  cookies: async () => ({ get: mocks.cookieGet }),
}));

vi.mock('@/components/public/PublicShell', () => ({
  PublicShell: (props: {
    initialLocale: string;
    signedIn: boolean;
    children: ReactNode;
  }) => {
    mocks.shellProps(props);
    return createElement('div', null, props.children);
  },
}));

import PublicLayout from './layout';

beforeEach(() => {
  mocks.cookieGet.mockReset();
  mocks.shellProps.mockReset();
});

describe('public legal-page layout', () => {
  it('passes the saved locale and signed-in affordance to PublicShell', async () => {
    mocks.cookieGet.mockImplementation((name: string) => {
      if (name === 'kinsun_ui_locale') return { value: 'en' };
      if (name.includes('kinsun_access_token')) return { value: 'synthetic-access-token' };
      return undefined;
    });

    const layout = await PublicLayout({ children: createElement('p', null, 'Synthetic content') });
    renderToStaticMarkup(layout);

    expect(mocks.shellProps).toHaveBeenCalledWith(
      expect.objectContaining({ initialLocale: 'en', signedIn: true }),
    );
  });

  it('falls back to Traditional Chinese and a sign-in affordance', async () => {
    mocks.cookieGet.mockImplementation((name: string) =>
      name === 'kinsun_ui_locale' ? { value: 'not-a-locale' } : undefined,
    );

    const layout = await PublicLayout({ children: createElement('p', null, 'Synthetic content') });
    renderToStaticMarkup(layout);

    expect(mocks.shellProps).toHaveBeenCalledWith(
      expect.objectContaining({ initialLocale: 'zh-Hant', signedIn: false }),
    );
  });
});
