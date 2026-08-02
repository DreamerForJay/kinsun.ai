import { describe, expect, it } from 'vitest';
import { toVoiceSessionLanguagePreference } from './language-route';

describe('toVoiceSessionLanguagePreference', () => {
  it.each([
    ['zh-TW', 'ZH_TW'],
    ['en-US', 'EN_US'],
    ['nan-TW', 'NAN_TW'],
    ['hak-TW', 'HAK_TW'],
  ] as const)('maps %s to %s', (language, expected) => {
    expect(toVoiceSessionLanguagePreference(language)).toBe(expected);
  });
});
