import { NextRequest, NextResponse } from 'next/server';
import { bffError } from '@/lib/server/bff-response';
import { buildGoogleAuthorizationUrl, getCognitoOAuthConfig } from '@/lib/server/cognito-oauth';
import {
  createOAuthTransaction,
  normalizeInvitationCode,
  onboardingIntent,
  oauthTransactionCookieName,
  oauthTransactionCookieOptions,
  serializeOAuthTransaction,
  strictRelativeReturnTo,
} from '@/lib/server/oauth-transaction';
import { isTrustedRequestOrigin } from '@/lib/server/auth-cookie';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

function noStore(response: NextResponse): NextResponse {
  response.headers.set('Cache-Control', 'no-store');
  response.headers.set('X-Content-Type-Options', 'nosniff');
  return response;
}

function beginLogin(
  request: NextRequest,
  rawReturnTo: string | null,
  rawIntent: unknown,
  rawInvitationCode?: unknown,
): Response {
  const returnTo = strictRelativeReturnTo(rawReturnTo);
  const intent = onboardingIntent(rawIntent);
  const invitationCode = normalizeInvitationCode(rawInvitationCode);
  if (returnTo === null) {
    return bffError(400, 'bad_request', 'Invalid sign-in return path', 'INVALID_RETURN_TO');
  }
  if (!intent || invitationCode === null || (intent !== 'FAMILY' && invitationCode !== undefined)) {
    return bffError(400, 'bad_request', 'Invalid sign-in request', 'INVALID_SIGN_IN_REQUEST');
  }

  try {
    const transaction = createOAuthTransaction(returnTo, intent, invitationCode);
    const response = noStore(
      NextResponse.redirect(buildGoogleAuthorizationUrl(getCognitoOAuthConfig(), transaction), {
        status: 303,
      }),
    );
    response.cookies.set(
      oauthTransactionCookieName(),
      serializeOAuthTransaction(transaction),
      oauthTransactionCookieOptions(),
    );
    return response;
  } catch {
    return bffError(
      503,
      'service_unavailable',
      'Sign-in is temporarily unavailable',
      'AUTH_CONFIGURATION_UNAVAILABLE',
      true,
    );
  }
}

export async function POST(request: NextRequest): Promise<Response> {
  if (!isTrustedRequestOrigin(request)) {
    return bffError(403, 'forbidden', 'Request origin rejected', 'CSRF_ORIGIN_REJECTED');
  }
  if (
    !request.headers
      .get('content-type')
      ?.toLowerCase()
      .startsWith('application/x-www-form-urlencoded')
  ) {
    return bffError(415, 'unsupported_media_type', 'Form request required', 'FORM_REQUIRED');
  }
  const form = await request.formData().catch(() => null);
  if (!form)
    return bffError(400, 'bad_request', 'Invalid sign-in request', 'INVALID_SIGN_IN_REQUEST');
  return beginLogin(
    request,
    typeof form.get('returnTo') === 'string' ? String(form.get('returnTo')) : null,
    form.get('intent'),
    form.get('invitationCode'),
  );
}
