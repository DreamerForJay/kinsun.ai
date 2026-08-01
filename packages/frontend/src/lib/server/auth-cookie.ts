const DEVELOPMENT_ACCESS_TOKEN_COOKIE = 'kinsun_access_token';
const PRODUCTION_ACCESS_TOKEN_COOKIE = '__Host-kinsun_access_token';

// Leave room for the cookie name and attributes under the browser's usual
// per-cookie limit. Cognito access tokens are expected to fit comfortably.
const MAX_ACCESS_TOKEN_LENGTH = 3072;

export function accessTokenCookieName(): string {
  return process.env.NODE_ENV === 'production'
    ? PRODUCTION_ACCESS_TOKEN_COOKIE
    : DEVELOPMENT_ACCESS_TOKEN_COOKIE;
}

export function accessTokenCookieOptions(maxAgeSeconds?: number) {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax' as const,
    path: '/',
    ...(maxAgeSeconds === undefined ? {} : { maxAge: maxAgeSeconds }),
  };
}

export function normalizeAccessToken(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const token = value.trim();
  if (!token || token.length > MAX_ACCESS_TOKEN_LENGTH || /\s/.test(token)) return null;
  return token;
}

function normalizeOrigin(value: string): string | null {
  try {
    const url = new URL(value);
    if (url.username || url.password || (url.protocol !== 'http:' && url.protocol !== 'https:')) {
      return null;
    }
    return url.origin;
  } catch {
    return null;
  }
}

/**
 * Cookie-authenticated state changes must originate from this frontend.
 * Production fails closed until FRONTEND_ORIGIN is explicitly configured.
 */
export function isTrustedRequestOrigin(request: Request): boolean {
  const suppliedOrigin = request.headers.get('origin');
  if (!suppliedOrigin) return false;

  const configuredOrigin = process.env.FRONTEND_ORIGIN;
  if (process.env.NODE_ENV === 'production' && !configuredOrigin) return false;

  const expectedOrigin = normalizeOrigin(configuredOrigin ?? new URL(request.url).origin);
  return expectedOrigin !== null && normalizeOrigin(suppliedOrigin) === expectedOrigin;
}
