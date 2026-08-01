import type { NextRequest } from 'next/server';
import { accessTokenCookieName, isTrustedRequestOrigin, normalizeAccessToken } from './auth-cookie';
import { bffError } from './bff-response';

const SAFE_METHODS = new Set(['GET', 'HEAD']);
const REQUEST_HEADERS = ['accept', 'content-type', 'idempotency-key', 'if-match'] as const;
const RESPONSE_HEADERS = ['content-type', 'content-disposition', 'retry-after'] as const;
const RESTRICTED_QUERY_KEYS = new Set(['token', 'access_token', 'id_token', 'refresh_token']);
const MAX_REQUEST_BODY_BYTES = 1_048_576;
const CORE_TIMEOUT_MS = 30_000;

function coreApiBaseUrl(): URL | null {
  try {
    const url = new URL(process.env.CORE_API_INTERNAL_URL ?? 'http://127.0.0.1:8000');
    if (url.username || url.password || (url.protocol !== 'http:' && url.protocol !== 'https:')) {
      return null;
    }
    url.pathname = `${url.pathname.replace(/\/+$/, '')}/`;
    url.search = '';
    url.hash = '';
    return url;
  } catch {
    return null;
  }
}

function targetUrl(request: NextRequest, path: string[]): URL | null {
  if (
    path.length === 0 ||
    path.some((segment) => !segment || segment === '.' || segment === '..')
  ) {
    return null;
  }

  for (const key of request.nextUrl.searchParams.keys()) {
    if (RESTRICTED_QUERY_KEYS.has(key.toLowerCase())) return null;
  }

  const base = coreApiBaseUrl();
  if (!base) return null;
  const encodedPath = path.map((segment) => encodeURIComponent(segment)).join('/');
  const target = new URL(encodedPath, base);
  target.search = request.nextUrl.search;
  return target;
}

function requestHeaders(request: NextRequest, accessToken: string): Headers {
  const headers = new Headers();
  for (const name of REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value !== null) headers.set(name, value);
  }
  headers.set('Authorization', `Bearer ${accessToken}`);
  return headers;
}

async function requestBody(request: NextRequest): Promise<ArrayBuffer | undefined | null> {
  if (SAFE_METHODS.has(request.method)) return undefined;

  const declaredLength = request.headers.get('content-length');
  if (declaredLength !== null) {
    const parsedLength = Number(declaredLength);
    if (
      !Number.isSafeInteger(parsedLength) ||
      parsedLength < 0 ||
      parsedLength > MAX_REQUEST_BODY_BYTES
    ) {
      return null;
    }
  }

  const body = await request.arrayBuffer();
  if (body.byteLength > MAX_REQUEST_BODY_BYTES) return null;
  return body.byteLength === 0 ? undefined : body;
}

export async function proxyCoreRequest(request: NextRequest, path: string[]): Promise<Response> {
  const accessToken = normalizeAccessToken(request.cookies.get(accessTokenCookieName())?.value);
  if (!accessToken) {
    return bffError(401, 'unauthorized', 'Authentication required', 'AUTHENTICATION_REQUIRED');
  }

  if (!SAFE_METHODS.has(request.method) && !isTrustedRequestOrigin(request)) {
    return bffError(403, 'forbidden', 'Request origin rejected', 'CSRF_ORIGIN_REJECTED');
  }

  const target = targetUrl(request, path);
  if (!target) {
    return bffError(400, 'bad_request', 'Invalid proxy request', 'INVALID_PROXY_REQUEST');
  }

  const body = await requestBody(request);
  if (body === null) {
    return bffError(413, 'payload_too_large', 'Request body is too large', 'PAYLOAD_TOO_LARGE');
  }

  try {
    const upstream = await fetch(target, {
      method: request.method,
      headers: requestHeaders(request, accessToken),
      body,
      cache: 'no-store',
      redirect: 'manual',
      signal: AbortSignal.timeout(CORE_TIMEOUT_MS),
    });
    const headers = new Headers({
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff',
    });
    for (const name of RESPONSE_HEADERS) {
      const value = upstream.headers.get(name);
      if (value !== null) headers.set(name, value);
    }
    return new Response(upstream.body, { status: upstream.status, headers });
  } catch (error) {
    const timedOut = error instanceof DOMException && error.name === 'TimeoutError';
    return bffError(
      timedOut ? 504 : 502,
      timedOut ? 'gateway_timeout' : 'bad_gateway',
      timedOut ? 'Core API timed out' : 'Core API is unavailable',
      timedOut ? 'CORE_API_TIMEOUT' : 'CORE_API_UNAVAILABLE',
      true,
    );
  }
}
