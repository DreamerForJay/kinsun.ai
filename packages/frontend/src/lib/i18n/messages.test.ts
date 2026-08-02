import { describe, expect, it } from 'vitest';
import { parseLocaleCookie } from './locale-cookie';
import {
  DEFAULT_LOCALE,
  LOCALES,
  MESSAGES,
  isLocale,
  localeTag,
  translate,
  type MessageKey,
} from './messages';

function placeholders(template: string): string[] {
  return [...template.matchAll(/\{(\w+)\}/g)].map((match) => match[1]).sort();
}

const keys = Object.keys(MESSAGES[DEFAULT_LOCALE]) as MessageKey[];

describe('message catalogue', () => {
  it('defines every locale in LOCALES', () => {
    for (const locale of LOCALES) {
      expect(MESSAGES[locale], `missing catalogue for ${locale}`).toBeDefined();
    }
  });

  it('has identical key sets across locales', () => {
    const reference = [...keys].sort();
    for (const locale of LOCALES) {
      expect(Object.keys(MESSAGES[locale]).sort(), `key drift in ${locale}`).toEqual(reference);
    }
  });

  it('has no blank strings', () => {
    for (const locale of LOCALES) {
      for (const key of keys) {
        expect(MESSAGES[locale][key].trim(), `${locale}/${key} is blank`).not.toBe('');
      }
    }
  });

  /* The check that actually catches mistakes: a translator can easily drop
     `{count}` and leave a sentence that still reads fine but has lost its
     number. Key parity alone would not notice. */
  it('uses the same placeholders in every locale', () => {
    for (const key of keys) {
      const reference = placeholders(MESSAGES[DEFAULT_LOCALE][key]);
      for (const locale of LOCALES) {
        expect(
          placeholders(MESSAGES[locale][key]),
          `placeholder drift in ${locale}/${key}`,
        ).toEqual(reference);
      }
    }
  });

  /* MASTER.md §4.2: a workflow state must read as the same state everywhere, so
     each domain enum needs a label in both locales — not a raw enum leaking to
     the caregiver's screen. */
  it('labels every care-event status and confidence band', () => {
    const required: MessageKey[] = [
      'eventStatus.CANDIDATE',
      'eventStatus.NEEDS_REVIEW',
      'eventStatus.VERIFIED',
      'eventStatus.CORRECTED',
      'eventStatus.REJECTED',
      'eventStatus.EXCLUDED',
      'confidence.LOW',
      'confidence.MEDIUM',
      'confidence.HIGH',
    ];
    for (const key of required) {
      expect(keys).toContain(key);
    }
  });
});

describe('translate', () => {
  it('substitutes parameters', () => {
    expect(translate('zh-Hant', 'common.version', { version: 3 })).toBe('版本 3');
    expect(translate('en', 'common.version', { version: 3 })).toBe('Version 3');
  });

  it('substitutes every occurrence of a multi-parameter template', () => {
    expect(
      translate('en', 'family.weekSummary', { reports: 2, meals: 5, activities: 1 }),
    ).toContain('2 published report(s), covering 5 meal and 1 activity item(s)');
  });

  it('leaves an unknown placeholder verbatim so the omission is visible', () => {
    expect(translate('en', 'common.version', {})).toBe('Version {version}');
  });

  it('returns the template unchanged when no parameters are given', () => {
    expect(translate('en', 'dashboard.title')).toBe('Authorized elders');
  });
});

describe('locale helpers', () => {
  it('accepts only known locales', () => {
    expect(isLocale('en')).toBe(true);
    expect(isLocale('zh-Hant')).toBe(true);
    expect(isLocale('zh-Hans')).toBe(false);
    expect(isLocale(undefined)).toBe(false);
  });

  it('maps to BCP 47 tags for Intl', () => {
    expect(localeTag('en')).toBe('en-US');
    expect(localeTag('zh-Hant')).toBe('zh-TW');
  });

  /* A hostile or stale cookie must not select a catalogue that does not exist —
     `MESSAGES[locale]` would be undefined and every lookup would throw. */
  it('falls back to the default for absent or unknown cookie values', () => {
    expect(parseLocaleCookie(undefined)).toBe(DEFAULT_LOCALE);
    expect(parseLocaleCookie('')).toBe(DEFAULT_LOCALE);
    expect(parseLocaleCookie('fr')).toBe(DEFAULT_LOCALE);
    expect(parseLocaleCookie('__proto__')).toBe(DEFAULT_LOCALE);
    expect(parseLocaleCookie('en')).toBe('en');
  });
});
