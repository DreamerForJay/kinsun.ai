import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { LanguageSwitch } from '@/components/LanguageSwitch';
import { LocaleProvider } from '@/lib/i18n/locale-context';
import type { Locale } from '@/lib/i18n/messages';
import { PublicHeader } from './PublicHeader';

function renderInLocale(locale: Locale, child: ReturnType<typeof createElement>) {
  return renderToStaticMarkup(
    createElement(LocaleProvider, {
      initialLocale: locale,
      children: child,
    }),
  );
}

describe('public locale layout stability', () => {
  it.each(['zh-Hant', 'en'] as const)('reserves both selection-mark slots in %s', (locale) => {
    const html = renderInLocale(locale, createElement(LanguageSwitch, { compactLabel: true }));

    expect(html.match(/data-visible=/g)).toHaveLength(2);
    expect(html.match(/data-visible="true"/g)).toHaveLength(1);
    expect(html.match(/aria-pressed="true"/g)).toHaveLength(1);
    expect(html).toContain('data-visually-hidden="true"');
  });

  it.each([
    ['zh-Hant', '智慧長照 AI 陪伴系統', '小暖'],
    ['en', 'Smart Eldercare AI Companion', 'Xiao Nuan'],
  ] as const)('keeps a full accessible and compact visual brand in %s', (locale, full, compact) => {
    const html = renderInLocale(locale, createElement(PublicHeader, { signedIn: false }));

    expect(html).toContain(`aria-label="${full}"`);
    expect(html).toContain(full);
    expect(html).toContain(compact);
  });

  it('locks locale-independent public chrome geometry', () => {
    const headerCss = readFileSync(
      fileURLToPath(new URL('./PublicHeader.module.css', import.meta.url)),
      'utf8',
    );
    const footerCss = readFileSync(
      fileURLToPath(new URL('./PublicFooter.module.css', import.meta.url)),
      'utf8',
    );
    const switchCss = readFileSync(
      fileURLToPath(new URL('../LanguageSwitch.module.css', import.meta.url)),
      'utf8',
    );

    expect(headerCss).toMatch(/max-width:\s*1200px/);
    expect(headerCss).toMatch(/grid-template-columns:\s*4\.5rem 7rem 11\.25rem/);
    expect(headerCss).toMatch(/\.menuToggle\s*{[^}]*width:\s*9\.25rem/s);
    expect(headerCss).toMatch(/@media \(min-width:\s*768px\) and \(max-width:\s*1199px\)/);
    expect(headerCss).toMatch(/@media \(max-width:\s*767px\)/);
    expect(headerCss).not.toMatch(/text-overflow:\s*ellipsis/);
    expect(footerCss).toMatch(/\.footer\s*{[^}]*width:\s*100%/s);
    expect(switchCss).toMatch(/\.check\s*{[^}]*visibility:\s*hidden/s);
    expect(switchCss).toMatch(/\.check\[data-visible='true'\]\s*{[^}]*visibility:\s*visible/s);
  });
});
