import { type NextRequest, NextResponse } from 'next/server';
import {
  accessTokenCookieName,
  accessTokenCookieOptions,
  isTrustedRequestOrigin,
  normalizeAccessToken,
} from '@/lib/server/auth-cookie';
import { bffError } from '@/lib/server/bff-response';

export const dynamic = 'force-dynamic';

function isLocalDevelopmentRequest(request: NextRequest): boolean {
  if (process.env.NODE_ENV !== 'development') return false;
  const host = request.nextUrl.hostname.toLowerCase();
  return host === 'localhost' || host === '127.0.0.1' || host === '[::1]';
}

function noStore(response: NextResponse): NextResponse {
  response.headers.set('Cache-Control', 'no-store');
  response.headers.set('X-Content-Type-Options', 'nosniff');
  return response;
}

export function GET(request: NextRequest): Response {
  const accessToken = normalizeAccessToken(request.cookies.get(accessTokenCookieName())?.value);
  return noStore(NextResponse.json({ credential_present: accessToken !== null }));
}

/**
 * Temporary local-demo seam. Production Cognito must set the cookie from a
 * server-side authorization-code callback; arbitrary browser token injection
 * stays disabled in production.
 */
export async function POST(request: NextRequest): Promise<Response> {
  if (!isLocalDevelopmentRequest(request)) {
    return bffError(404, 'not_found', 'Resource not found', 'RESOURCE_NOT_FOUND');
  }
  if (!isTrustedRequestOrigin(request)) {
    return bffError(403, 'forbidden', 'Request origin rejected', 'CSRF_ORIGIN_REJECTED');
  }
  if (!request.headers.get('content-type')?.toLowerCase().startsWith('application/json')) {
    return bffError(415, 'unsupported_media_type', 'JSON request required', 'JSON_REQUIRED');
  }

  const payload = (await request.json().catch(() => null)) as { access_token?: unknown } | null;
  const accessToken = normalizeAccessToken(payload?.access_token);
  if (!accessToken) {
    return bffError(422, 'validation_error', 'Invalid access token', 'INVALID_ACCESS_TOKEN');
  }

  const response = noStore(NextResponse.json({ credential_present: true }, { status: 201 }));
  response.cookies.set(accessTokenCookieName(), accessToken, accessTokenCookieOptions());
  return response;
}

export function DELETE(request: NextRequest): Response {
  if (!isTrustedRequestOrigin(request)) {
    return bffError(403, 'forbidden', 'Request origin rejected', 'CSRF_ORIGIN_REJECTED');
  }

  const response = noStore(NextResponse.json({ credential_present: false }));
  response.cookies.set(accessTokenCookieName(), '', {
    ...accessTokenCookieOptions(),
    expires: new Date(0),
  });
  return response;
}
