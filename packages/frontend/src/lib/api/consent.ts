import { apiFetch, createIdempotencyKey, type ApiConfig } from './client';

export interface ConsentRecord {
  consent_id: string;
  purpose_code:
    | 'BASIC_VOICE'
    | 'TRANSCRIPT_STORAGE'
    | 'CARE_EVENT_EXTRACTION'
    | 'LONG_TERM_MEMORY'
    | 'COMPANION_SIGNAL_ANALYSIS'
    | 'PROACTIVE_COMPANION'
    | 'FAMILY_SHARING';
  consent_version: number;
  status: 'PENDING' | 'GRANTED' | 'REVOKED' | 'EXPIRED' | 'REJECTED';
  policy_version: string;
  effective_at: string;
  expires_at: string | null;
  revoked_at: string | null;
  affected_capabilities: string[];
  deletion_request_id: string | null;
}

interface ConsentList {
  items: ConsentRecord[];
}

export type ConsentApiConfig = ApiConfig;

export async function listConsents(config: ApiConfig, elderId: string): Promise<ConsentRecord[]> {
  const result = await apiFetch<ConsentList>(config, `/api/v1/elders/${elderId}/consents`);
  return result.items;
}

export function activeBasicVoiceConsent(items: ConsentRecord[]): ConsentRecord | null {
  return (
    items.find((item) => item.purpose_code === 'BASIC_VOICE' && item.status === 'GRANTED') ?? null
  );
}

export async function grantBasicVoiceConsent(
  config: ApiConfig,
  elderId: string,
  policyVersion: string,
): Promise<ConsentRecord> {
  const result = await apiFetch<ConsentList>(config, `/api/v1/elders/${elderId}/consents`, {
    method: 'POST',
    headers: { 'Idempotency-Key': createIdempotencyKey('consent-grant') },
    body: JSON.stringify({
      purposes: ['BASIC_VOICE'],
      share_scopes: [],
      actor_confirmation: true,
      policy_version: policyVersion,
    }),
  });
  const consent = activeBasicVoiceConsent(result.items);
  if (!consent) throw new Error('CORE_CONSENT_RESPONSE_MISSING_BASIC_VOICE');
  return consent;
}

export function revokeBasicVoiceConsent(
  config: ApiConfig,
  elderId: string,
  consentId: string,
): Promise<ConsentRecord> {
  return apiFetch(config, `/api/v1/elders/${elderId}/consents/${consentId}/revoke`, {
    method: 'POST',
    headers: { 'Idempotency-Key': createIdempotencyKey('consent-revoke') },
    body: JSON.stringify({
      reason_code: 'ELDER_REQUESTED_STOP',
      revoke_scope: [],
      request_deletion: false,
    }),
  });
}
