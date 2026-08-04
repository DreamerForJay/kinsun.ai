import { normalizeAccessToken } from './auth-cookie';
import type { CognitoTokenSet } from './cognito-oauth';
import { logAuthDiagnostic } from './auth-diagnostics';
import type { OAuthTransaction } from './oauth-transaction';

const CORE_ONBOARDING_TIMEOUT_MS = 10_000;

function idTokenClaimDiagnostics(idToken: string): Record<string, boolean | string> {
  try {
    const payloadPart = idToken.split('.')[1];
    if (!payloadPart) return { payload_valid: false };
    const claims = JSON.parse(Buffer.from(payloadPart, 'base64url').toString('utf8')) as Record<
      string,
      unknown
    >;
    return {
      payload_valid: true,
      audience_matches: claims.aud === process.env.COGNITO_WEB_CLIENT_ID,
      token_use_is_id: claims.token_use === 'id',
      email_present: typeof claims.email === 'string' && claims.email.trim().length > 0,
      email_verified_type: typeof claims.email_verified,
      email_verified_true: claims.email_verified === true,
      name_present: typeof claims.name === 'string' && claims.name.trim().length > 0,
    };
  } catch {
    return { payload_valid: false };
  }
}

function safeReasonCode(payload: unknown): string | null {
  if (!payload || typeof payload !== 'object') return null;
  const error = (payload as { error?: unknown }).error;
  if (!error || typeof error !== 'object') return null;
  const value = (error as { reason_code?: unknown }).reason_code;
  return typeof value === 'string' && /^[A-Z0-9_]{1,64}$/.test(value) ? value : null;
}

function safeHttpUrl(value: string | undefined): URL | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    if (url.username || url.password || (url.protocol !== 'http:' && url.protocol !== 'https:')) {
      return null;
    }
    return url;
  } catch {
    return null;
  }
}

function coreOnboardingUrl(): URL {
  const configured = process.env.CORE_ONBOARDING_REDEEM_URL;
  const target = safeHttpUrl(configured);
  const coreBase = safeHttpUrl(process.env.CORE_API_INTERNAL_URL);
  if (
    !target ||
    !coreBase ||
    target.origin !== coreBase.origin ||
    target.pathname !== '/api/v1/onboarding/resolve' ||
    target.search ||
    target.hash
  ) {
    throw new Error('Core onboarding endpoint is unavailable');
  }
  return target;
}

function coreMeUrl(): URL {
  const coreBase = safeHttpUrl(process.env.CORE_API_INTERNAL_URL);
  if (!coreBase || coreBase.search || coreBase.hash) {
    throw new Error('Core API endpoint is unavailable');
  }
  const target = new URL('/api/v1/me', coreBase);
  if (target.origin !== coreBase.origin) throw new Error('Core API endpoint is unavailable');
  return target;
}

/**
 * Resolve a new elder or invited family member in Core. It deliberately
 * receives the ID token only in this server-side call and never stores it.
 * Missing or cross-origin endpoint configuration fails closed.
 */
export async function redeemCoreOnboarding(
  tokenSet: CognitoTokenSet,
  transaction: OAuthTransaction,
): Promise<void> {
  // Existing family members sign in without a code and are resolved by Core
  // from the access token on /me. Only a join flow may create family access.
  if (
    transaction.intent === 'STAFF' ||
    (transaction.intent === 'FAMILY' && !transaction.invitationCode)
  ) {
    return;
  }
  const target = coreOnboardingUrl();

  const response = await fetch(target, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${tokenSet.idToken}`,
      'Content-Type': 'application/json',
      'Idempotency-Key': `oauth-${transaction.state}`,
    },
    body: JSON.stringify({
      intent: transaction.intent,
      ...(transaction.invitationCode ? { invitation_code: transaction.invitationCode } : {}),
    }),
    cache: 'no-store',
    redirect: 'error',
    signal: AbortSignal.timeout(CORE_ONBOARDING_TIMEOUT_MS),
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as unknown;
    logAuthDiagnostic('Core onboarding rejected', {
      status: response.status,
      reason_code: safeReasonCode(payload),
      ...idTokenClaimDiagnostics(tokenSet.idToken),
    });
    throw new Error('Core onboarding redemption failed');
  }
}

/**
 * LINE sign-in is allowed only for a Cognito subject that Core already maps
 * to an active Actor. This endpoint never creates or merges Actor records.
 */
export async function requireExistingCoreActor(rawAccessToken: unknown): Promise<void> {
  const accessToken = normalizeAccessToken(rawAccessToken);
  if (!accessToken) throw new Error('Cognito access token is unavailable');
  const response = await fetch(coreMeUrl(), {
    method: 'GET',
    headers: { Accept: 'application/json', Authorization: `Bearer ${accessToken}` },
    cache: 'no-store',
    redirect: 'error',
    signal: AbortSignal.timeout(CORE_ONBOARDING_TIMEOUT_MS),
  });
  if (!response.ok) {
    console.error('[auth] Existing Core Actor check rejected', { status: response.status });
    throw new Error('Existing Core Actor is required');
  }
}
