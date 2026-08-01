export type ConsentType = 'recording' | 'data_processing';

export interface ConsentApiConfig {
  apiBaseUrl: string;
  token: string;
}

async function postConsent(config: ConsentApiConfig, path: string, elderId: string, type: ConsentType): Promise<void> {
  const base = config.apiBaseUrl.replace(/\/+$/, '');
  const response = await fetch(`${base}${path}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${config.token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ elderId, type }),
  });
  if (!response.ok) {
    throw new Error(`CONSENT_REQUEST_FAILED: ${response.status}`);
  }
}

/** POST /v1/consent/grant (A06.1, A06.3). */
export function grantConsent(config: ConsentApiConfig, elderId: string, type: ConsentType = 'recording'): Promise<void> {
  return postConsent(config, '/v1/consent/grant', elderId, type);
}

/** POST /v1/consent/revoke — stops future recording; existing data is handled per retention policy (A06.4). */
export function revokeConsent(config: ConsentApiConfig, elderId: string, type: ConsentType = 'recording'): Promise<void> {
  return postConsent(config, '/v1/consent/revoke', elderId, type);
}
