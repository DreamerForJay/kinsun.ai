import { hasAuthCredential } from './auth-session';
import type { ApiConfig } from './api/client';

export interface RuntimeConfig extends ApiConfig {
  apiBaseUrl: string;
  elderId: string;
  caregiverId: string;
  consentPolicyVersion: string;
  credentialStatus: 'present' | 'missing' | 'unavailable';
}

/**
 * Elder/caregiver IDs select a resource; they are not trusted credentials.
 * Core reauthorizes their scope on every request. Authentication tokens never
 * appear here and are never readable by browser JavaScript.
 */
export const AUTH_STORAGE_KEYS = {
  elderId: 'elderly_care_elder_id',
  caregiverId: 'elderly_care_caregiver_id',
} as const;

const LEGACY_TOKEN_STORAGE_KEY = 'elderly_care_id_token';

export function clearLegacyBrowserCredential(): void {
  if (typeof window !== 'undefined') window.localStorage.removeItem(LEGACY_TOKEN_STORAGE_KEY);
}

/**
 * Reads non-secret target IDs locally, then asks the same-origin BFF whether
 * an HttpOnly credential cookie exists. Presence is not proof that the token
 * is valid; Core remains the authentication and authorization authority.
 */
export async function getRuntimeConfig(): Promise<RuntimeConfig> {
  const apiBaseUrl = '/backend/core';
  const consentPolicyVersion = process.env.NEXT_PUBLIC_CONSENT_POLICY_VERSION ?? '';

  if (typeof window === 'undefined') {
    return {
      apiBaseUrl,
      elderId: '',
      caregiverId: '',
      consentPolicyVersion,
      credentialStatus: 'unavailable',
    };
  }

  // Do not silently migrate a JavaScript-readable credential into the new
  // session. Remove the legacy copy and require an explicit new login.
  clearLegacyBrowserCredential();
  const elderId = window.localStorage.getItem(AUTH_STORAGE_KEYS.elderId) ?? '';
  const caregiverId = window.localStorage.getItem(AUTH_STORAGE_KEYS.caregiverId) ?? '';
  let credentialStatus: RuntimeConfig['credentialStatus'] = 'unavailable';
  try {
    credentialStatus = (await hasAuthCredential()) ? 'present' : 'missing';
  } catch {
    // Fail closed without claiming that the user is logged out when the BFF
    // itself is unavailable.
  }
  return { apiBaseUrl, elderId, caregiverId, consentPolicyVersion, credentialStatus };
}
