import { DEFAULT_LOCALE, isLocale, type Locale } from './messages';

/**
 * UI language preference.
 *
 * Deliberately NOT httpOnly: it is a display preference, not a credential, and
 * the client needs to write it. It is also never forwarded upstream —
 * `lib/server/core-proxy.ts` builds its request headers from a fixed allowlist
 * and sends no cookies at all, so this value cannot reach the Core API and
 * cannot be mistaken for the elder's domain language preference (ADR 0006 §5).
 */
export const LOCALE_COOKIE = 'kinsun_ui_locale';

const ONE_YEAR_SECONDS = 60 * 60 * 24 * 365;

/** Falls back to the default for absent, malformed, or unknown values. */
export function parseLocaleCookie(value: string | undefined): Locale {
  return isLocale(value) ? value : DEFAULT_LOCALE;
}

export function localeCookieAttributes(locale: Locale, secure: boolean): string {
  const attributes = [
    `${LOCALE_COOKIE}=${locale}`,
    'Path=/',
    `Max-Age=${ONE_YEAR_SECONDS}`,
    'SameSite=Lax',
  ];
  if (secure) attributes.push('Secure');
  return attributes.join('; ');
}
