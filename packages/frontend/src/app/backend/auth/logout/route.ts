import { NextRequest, NextResponse } from 'next/server';
import {
  accessTokenCookieName,
  accessTokenCookieOptions,
  isTrustedRequestOrigin,
} from '@/lib/server/auth-cookie';
import { bffError } from '@/lib/server/bff-response';
import { buildCognitoLogoutUrl, getCognitoOAuthConfig } from '@/lib/server/cognito-oauth';
import {
  oauthTransactionCookieName,
  oauthTransactionCookieOptions,
} from '@/lib/server/oauth-transaction';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

function noStore(response: NextResponse): NextResponse {
  response.headers.set('Cache-Control', 'no-store');
  response.headers.set('X-Content-Type-Options', 'nosniff');
  return response;
}

export function POST(request: NextRequest): Response {
  if (!isTrustedRequestOrigin(request)) {
    return bffError(403, 'forbidden', 'Request origin rejected', 'CSRF_ORIGIN_REJECTED');
  }

  let response: NextResponse;
  try {
    response = NextResponse.redirect(buildCognitoLogoutUrl(getCognitoOAuthConfig()), {
      status: 303,
    });
  } catch {
    response = new NextResponse(null, { status: 303, headers: { Location: '/sign-in' } });
  }
  response.cookies.set(accessTokenCookieName(), '', {
    ...accessTokenCookieOptions(),
    expires: new Date(0),
  });
  response.cookies.set(oauthTransactionCookieName(), '', {
    ...oauthTransactionCookieOptions(),
    expires: new Date(0),
    maxAge: 0,
  });
  return noStore(response);
}
