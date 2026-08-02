import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { LocaleProvider } from '@/lib/i18n/locale-context';
import type { Locale } from '@/lib/i18n/messages';
import { LEGAL_PAGE_IDS, LegalPage, type LegalPageId } from './LegalPage';

const EXPECTED_TITLES: Record<Locale, Record<LegalPageId, string>> = {
  'zh-Hant': {
    privacy: '隱私權政策',
    terms: '服務條款',
    dataRights: '資料權利',
    accessibility: '無障礙聲明',
  },
  en: {
    privacy: 'Privacy Policy',
    terms: 'Terms of Service',
    dataRights: 'Data Rights',
    accessibility: 'Accessibility Statement',
  },
};

describe('public legal pages', () => {
  for (const locale of ['zh-Hant', 'en'] as const) {
    for (const page of LEGAL_PAGE_IDS) {
      it(`renders ${page} in ${locale} with one document outline`, () => {
        const html = renderToStaticMarkup(
          createElement(LocaleProvider, {
            initialLocale: locale,
            children: createElement(LegalPage, { page }),
          }),
        );

        expect(html).toContain(`data-legal-document="${page}"`);
        expect(html).toContain(EXPECTED_TITLES[locale][page]);
        expect(html.match(/<h1/g)).toHaveLength(1);
        expect((html.match(/<h2/g) ?? []).length).toBeGreaterThanOrEqual(5);
        expect(html).not.toContain('<main');
        expect(html).not.toContain('<p class="">');
      });
    }
  }

  it('locks the family-style reading width without unsafe fixed content height', () => {
    const cssPath = fileURLToPath(new URL('./LegalPage.module.css', import.meta.url));
    const css = readFileSync(cssPath, 'utf8');

    expect(css).toMatch(/max-width:\s*720px/);
    expect(css).not.toMatch(/#[0-9a-f]{3,8}\b/i);
    expect(css).not.toMatch(/(^|\n)\s*height\s*:/);
    expect(css).not.toMatch(/overflow:\s*hidden/);
  });
});
