import { NextRequest, NextResponse } from 'next/server';
import { accessTokenCookieName, accessTokenCookieOptions } from '@/lib/server/auth-cookie';
import { exchangeAuthorizationCode, getCognitoOAuthConfig } from '@/lib/server/cognito-oauth';
import { redeemCoreOnboarding } from '@/lib/server/core-onboarding';
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

function failedCallback(): Response {
  return clearTransaction(noStore(sameOriginRedirect('/sign-in?error=oauth_failed')));
}

export async function GET(request: NextRequest): Promise<Response> {
  const codes = request.nextUrl.searchParams.getAll('code');
  const states = request.nextUrl.searchParams.getAll('state');
  if (codes.length !== 1 || states.length !== 1 || request.nextUrl.searchParams.has('error')) {
    return failedCallback();
  }

  const transaction = parseOAuthTransaction(
    request.cookies.get(oauthTransactionCookieName())?.value,
  );
  if (!transaction || !stateMatches(transaction, states[0] ?? null)) return failedCallback();

  let stage: 'token_exchange' | 'core_onboarding' = 'token_exchange';
  try {
    const tokenSet = await exchangeAuthorizationCode(
      getCognitoOAuthConfig(),
      codes[0] ?? '',
      transaction,
    );
    stage = 'core_onboarding';
    await redeemCoreOnboarding(tokenSet, transaction);
    const response = clearTransaction(noStore(sameOriginRedirect(transaction.returnTo)));
    response.cookies.set(
      accessTokenCookieName(),
      tokenSet.accessToken,
      accessTokenCookieOptions(tokenSet.expiresIn),
    );
    return response;
  } catch {
    console.error('[auth] OAuth callback failed', { stage });
    return failedCallback();
  }
}
