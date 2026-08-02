import type { SpeechLanguage } from './speech-gateway-client';

/** Core's persisted language-route names for each language the voice UI offers. */
export type VoiceSessionLanguagePreference = 'ZH_TW' | 'EN_US' | 'NAN_TW' | 'HAK_TW';

const VOICE_SESSION_LANGUAGE_PREFERENCES = {
  'zh-TW': 'ZH_TW',
  'en-US': 'EN_US',
  'nan-TW': 'NAN_TW',
  'hak-TW': 'HAK_TW',
} as const satisfies Record<SpeechLanguage, VoiceSessionLanguagePreference>;

/**
 * The sole browser-to-Core language mapping. Keep speech-provider language tags
 * at the UI boundary and translate them only when creating the Core session.
 */
export function toVoiceSessionLanguagePreference(
  language: SpeechLanguage,
): VoiceSessionLanguagePreference {
  return VOICE_SESSION_LANGUAGE_PREFERENCES[language];
}
