export interface RuntimeConfig {
  apiBaseUrl: string;
  wsUrl: string;
  token: string;
  elderId: string;
  caregiverId: string;
}

/**
 * Single source of truth for the localStorage keys every page reads/writes
 * auth state through — /dev-login is the only place that sets them, every
 * other page only reads. Keeping the key strings here (not re-typed at each
 * call site) avoids the class of bug where a page reads a typo'd key and
 * silently sees "not logged in" instead of a real value.
 */
export const AUTH_STORAGE_KEYS = {
  token: 'elderly_care_id_token',
  elderId: 'elderly_care_elder_id',
  caregiverId: 'elderly_care_caregiver_id',
  consentGranted: 'elderly_care_consent_granted',
} as const;

/**
 * Reads the values the voice UI needs to talk to the backend. Cognito
 * sign-in (Hosted UI / Amplify) isn't part of this task list — until it's
 * wired in, the ID token and elderId are expected in localStorage (set via
 * /dev-login) or NEXT_PUBLIC_* env vars for local demo/dev use. This is
 * intentionally the one seam a real auth integration should replace, rather
 * than something scattered across components.
 */
export function getRuntimeConfig(): RuntimeConfig {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? '';
  const wsUrl = process.env.NEXT_PUBLIC_WS_URL ?? '';

  if (typeof window === 'undefined') {
    return { apiBaseUrl, wsUrl, token: '', elderId: '', caregiverId: '' };
  }

  const token = window.localStorage.getItem(AUTH_STORAGE_KEYS.token) ?? '';
  const elderId = window.localStorage.getItem(AUTH_STORAGE_KEYS.elderId) ?? '';
  const caregiverId = window.localStorage.getItem(AUTH_STORAGE_KEYS.caregiverId) ?? '';
  return { apiBaseUrl, wsUrl, token, elderId, caregiverId };
}
