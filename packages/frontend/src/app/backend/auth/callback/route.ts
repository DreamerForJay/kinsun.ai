import { NextRequest, NextResponse } from 'next/server';
import { accessTokenCookieName, accessTokenCookieOptions } from '@/lib/server/auth-cookie';
import { logAuthDiagnostic } from '@/lib/server/auth-diagnostics';
import { exchangeAuthorizationCode, getCognitoOAuthConfig } from '@/lib/server/cognito-oauth';
import { redeemCoreOnboarding, requireExistingCoreActor } from '@/lib/server/core-onboarding';
import {
  oauthTransactionCookieName,
  oauthTransactionCookieOptions,
  parseOAuthTransaction,
  stateMatches,
} from '@/lib/server/oauth-transaction';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

function noStore(response: NextResponse): NextResponse {
  response.headers.set('Cache-Control', 'no-store');
  response.headers.set('X-Content-Type-Options', 'nosniff');
  return response;
}

function clearTransaction(response: NextResponse): NextResponse {
  response.cookies.set(oauthTransactionCookieName(), '', {
    ...oauthTransactionCookieOptions(),
    expires: new Date(0),
    maxAge: 0,
  });
  return response;
}

function sameOriginRedirect(location: string): NextResponse {
  return new NextResponse(null, { status: 303, headers: { Location: location } });
}

function failedCallback(clearCurrentTransaction = true): Response {
  const response = noStore(sameOriginRedirect('/sign-in?error=oauth_failed'));
  return clearCurrentTransaction ? clearTransaction(response) : response;
}

const LOGGABLE_OAUTH_ERROR_CODES = new Set([
  'access_denied',
  'account_selection_required',
  'consent_required',
  'interaction_required',
  'invalid_request',
  'invalid_request_object',
  'invalid_request_uri',
  'invalid_scope',
  'login_required',
  'request_not_supported',
  'request_uri_not_supported',
  'server_error',
  'temporarily_unavailable',
  'unauthorized_client',
  'unsupported_response_type',
]);

/**
 * Only standard OAuth/OIDC error identifiers are safe to log. Unknown values
 * collapse to one bounded label so an attacker cannot inject free text or
 * create unbounded log cardinality. `error_description` is never read here.
 */
function safeOAuthErrorCode(value: string | null): string {
  return value !== null && LOGGABLE_OAUTH_ERROR_CODES.has(value) ? value : 'unrecognised';
}

export async function GET(request: NextRequest): Promise<Response> {
  const codes = request.nextUrl.searchParams.getAll('code');
  const states = request.nextUrl.searchParams.getAll('state');
  const errors = request.nextUrl.searchParams.getAll('error');
  const transactionCookie = request.cookies.get(oauthTransactionCookieName())?.value;
  const transaction = parseOAuthTransaction(transactionCookie);
  const callbackOwnsCurrentTransaction =
    transaction !== null &&
    states.length === 1 &&
    stateMatches(transaction, states[0] ?? null);
  /* A missing/invalid cookie is safe to expire. A valid cookie is cleared only
     when this callback proves ownership with its state. Otherwise a delayed
     callback from login A could erase the newer transaction for login B. */
  const clearCurrentTransaction = transaction === null || callbackOwnsCurrentTransaction;
  /* These two branches used to return without logging anything, which made a
     failed second sign-in indistinguishable from a failed first one: the user
     saw "這次登入沒有完成" and the server said nothing at all. Both are now
     reported, because which one fires is the whole diagnosis. */
  if (errors.length > 0) {
    logAuthDiagnostic('OAuth callback failed', {
      stage: 'provider_error',
      oauth_error: safeOAuthErrorCode(errors.length === 1 ? (errors[0] ?? null) : null),
      error_count: errors.length,
      current_transaction_preserved: !clearCurrentTransaction,
    });
    return failedCallback(clearCurrentTransaction);
  }
  if (codes.length !== 1 || states.length !== 1) {
    logAuthDiagnostic('OAuth callback failed', {
      stage: 'malformed_redirect',
      code_count: codes.length,
      state_count: states.length,
      current_transaction_preserved: !clearCurrentTransaction,
    });
    return failedCallback(clearCurrentTransaction);
  }

  if (!transaction || !callbackOwnsCurrentTransaction) {
    logAuthDiagnostic('OAuth callback failed', {
      stage: 'transaction',
      cookie_present: Boolean(transactionCookie),
      transaction_valid: Boolean(transaction),
      state_matches: false,
      current_transaction_preserved: !clearCurrentTransaction,
    });
    return failedCallback(clearCurrentTransaction);
  }

  let stage: 'token_exchange' | 'core_onboarding' | 'core_actor_check' = 'token_exchange';
  try {
    const tokenSet = await exchangeAuthorizationCode(
      getCognitoOAuthConfig(),
      codes[0] ?? '',
      transaction,
    );
    if (transaction.provider === 'LINE') {
      stage = 'core_actor_check';
      await requireExistingCoreActor(tokenSet.accessToken);
    } else {
      stage = 'core_onboarding';
      await redeemCoreOnboarding(tokenSet, transaction);
    }
    const response = clearTransaction(noStore(sameOriginRedirect(transaction.returnTo)));
    response.cookies.set(
      accessTokenCookieName(),
      tokenSet.accessToken,
      accessTokenCookieOptions(tokenSet.expiresIn),
    );
    return response;
  } catch {
    logAuthDiagnostic('OAuth callback failed', { stage });
    return failedCallback();
  }
}
