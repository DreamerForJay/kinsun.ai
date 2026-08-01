import { NextRequest } from 'next/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { POST as createSession } from '../../app/backend/auth/session/route';
import { accessTokenCookieName, accessTokenCookieOptions } from './auth-cookie';
import { proxyCoreRequest } from './core-proxy';

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function request(
  path: string,
  init: ConstructorParameters<typeof NextRequest>[1] = {},
): NextRequest {
  return new NextRequest(`http://localhost${path}`, init);
}

describe('HttpOnly authentication session', () => {
  it('sets a development credential with hardened cookie attributes', async () => {
    vi.stubEnv('NODE_ENV', 'development');
    const response = await createSession(
      request('/backend/auth/session', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Origin: 'http://localhost',
        },
        body: JSON.stringify({ access_token: 'synthetic-test-token' }),
      }),
    );

    expect(response.status).toBe(201);
    const setCookie = response.headers.get('set-cookie') ?? '';
    expect(setCookie).toContain('kinsun_access_token=synthetic-test-token');
    expect(setCookie).toContain('Path=/');
    expect(setCookie).toContain('HttpOnly');
    expect(setCookie).toContain('SameSite=lax');
    expect(setCookie).not.toContain('Secure');
    expect(await response.text()).not.toContain('synthetic-test-token');
  });

  it('does not expose the arbitrary token setter in production', async () => {
    vi.stubEnv('NODE_ENV', 'production');
    vi.stubEnv('FRONTEND_ORIGIN', 'https://care.example');
    const response = await createSession(
      request('/backend/auth/session', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Origin: 'http://localhost',
        },
        body: JSON.stringify({ access_token: 'synthetic-test-token' }),
      }),
    );

    expect(response.status).toBe(404);
    expect(response.headers.get('set-cookie')).toBeNull();
  });

  it('uses the Secure __Host cookie profile in production', () => {
    vi.stubEnv('NODE_ENV', 'production');

    expect(accessTokenCookieName()).toBe('__Host-kinsun_access_token');
    expect(accessTokenCookieOptions()).toMatchObject({
      httpOnly: true,
      secure: true,
      sameSite: 'lax',
      path: '/',
    });
  });
});

describe('Core BFF proxy', () => {
  it('turns the HttpOnly cookie into a server-side Bearer header', async () => {
    vi.stubEnv('NODE_ENV', 'development');
    vi.stubEnv('CORE_API_INTERNAL_URL', 'http://127.0.0.1:8000');
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      Response.json({ data: { ok: true }, meta: {} }, { status: 200 }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const response = await proxyCoreRequest(
      request('/backend/core/api/v1/example?cursor=opaque', {
        headers: {
          Cookie: 'kinsun_access_token=synthetic-test-token',
          Authorization: 'Bearer browser-supplied-token',
        },
      }),
      ['api', 'v1', 'example'],
    );

    expect(response.status).toBe(200);
    const [target, init] = fetchMock.mock.calls[0];
    expect(String(target)).toBe('http://127.0.0.1:8000/api/v1/example?cursor=opaque');
    const headers = new Headers(init?.headers);
    expect(headers.get('Authorization')).toBe('Bearer synthetic-test-token');
    expect(headers.has('Cookie')).toBe(false);
  });

  it('fails closed before contacting Core when the cookie is missing', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const response = await proxyCoreRequest(request('/backend/core/api/v1/example'), [
      'api',
      'v1',
      'example',
    ]);

    expect(response.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('fails closed when the credential cookie is malformed', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const response = await proxyCoreRequest(
      request('/backend/core/api/v1/example', {
        headers: { Cookie: `kinsun_access_token=${'a'.repeat(3073)}` },
      }),
      ['api', 'v1', 'example'],
    );

    expect(response.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('rejects cross-origin state changes', async () => {
    vi.stubEnv('NODE_ENV', 'development');
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const response = await proxyCoreRequest(
      request('/backend/core/api/v1/example', {
        method: 'POST',
        headers: {
          Cookie: 'kinsun_access_token=synthetic-test-token',
          Origin: 'https://attacker.example',
          'Content-Type': 'application/json',
        },
        body: '{}',
      }),
      ['api', 'v1', 'example'],
    );

    expect(response.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('rejects credentials in a proxied query string', async () => {
    vi.stubEnv('NODE_ENV', 'development');
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const response = await proxyCoreRequest(
      request('/backend/core/api/v1/example?access_token=leak', {
        headers: { Cookie: 'kinsun_access_token=synthetic-test-token' },
      }),
      ['api', 'v1', 'example'],
    );

    expect(response.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
