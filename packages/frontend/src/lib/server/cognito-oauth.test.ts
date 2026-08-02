import { NextRequest } from 'next/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { GET as callback } from '../../app/backend/auth/callback/route';
import { POST as login } from '../../app/backend/auth/login/route';
import { POST as logout } from '../../app/backend/auth/logout/route';
import {
  createOAuthTransaction,
  oauthTransactionCookieName,
  parseOAuthTransaction,
  serializeOAuthTransaction,
  strictRelativeReturnTo,
} from './oauth-transaction';

const transactionSecret = 'synthetic-transaction-secret-long-enough';

function request(
  path: string,
  init: ConstructorParameters<typeof NextRequest>[1] = {},
): NextRequest {
  return new NextRequest(`http://localhost:3000${path}`, init);
}

function configureOAuth(): void {
  vi.stubEnv('NODE_ENV', 'development');
  vi.stubEnv('FRONTEND_ORIGIN', 'http://localhost:3000');
  vi.stubEnv('COGNITO_OAUTH_DOMAIN', 'https://example.auth.us-west-2.amazoncognito.com');
  vi.stubEnv('COGNITO_WEB_CLIENT_ID', 'web-client-id');
  vi.stubEnv('COGNITO_CALLBACK_URL', 'http://localhost:3000/backend/auth/callback');
  vi.stubEnv('COGNITO_LOGOUT_URL', 'http://localhost:3000/sign-in');
  vi.stubEnv('COGNITO_OAUTH_TRANSACTION_SECRET', transactionSecret);
  vi.stubEnv('CORE_API_INTERNAL_URL', 'http://127.0.0.1:8000');
  vi.stubEnv('CORE_ONBOARDING_REDEEM_URL', '');
}

function idToken(nonce: string): string {
  const header = Buffer.from(JSON.stringify({ alg: 'RS256', typ: 'JWT' })).toString('base64url');
  const payload = Buffer.from(JSON.stringify({ nonce })).toString('base64url');
  return `${header}.${payload}.signature`;
}

function cookieValue(response: Response, name: string): string | undefined {
  const header = response.headers.get('set-cookie') ?? '';
  return new RegExp(`(?:^|, )${name}=([^;]*)`).exec(header)?.[1];
}

function setCookieHeader(response: Response): string {
  return response.headers.get('set-cookie') ?? '';
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('Cognito OAuth transaction', () => {
  it('only accepts a strict relative return path', () => {
    expect(strictRelativeReturnTo('/family')).toBe('/family');
    expect(strictRelativeReturnTo('/family?next=https://attacker.example')).toBeNull();
    expect(strictRelativeReturnTo('/family#https://attacker.example')).toBeNull();
    expect(strictRelativeReturnTo('https://attacker.example')).toBeNull();
    expect(strictRelativeReturnTo('//attacker.example')).toBeNull();
    expect(strictRelativeReturnTo('/\\attacker.example')).toBeNull();
    expect(strictRelativeReturnTo('/not-an-approved-login-destination')).toBeNull();
  });

  it('keeps intent and a family invitation only in a signed short-lived transaction', () => {
    configureOAuth();
    const transaction = createOAuthTransaction(
      '/onboarding/resolve',
      'FAMILY',
      'family-invite-code',
    );
    const serialized = serializeOAuthTransaction(transaction);
    expect(parseOAuthTransaction(serialized)).toMatchObject({
      intent: 'FAMILY',
      invitationCode: 'family-invite-code',
      returnTo: '/onboarding/resolve',
    });
    expect(parseOAuthTransaction(`${serialized}tampered`)).toBeNull();
  });
});

describe('Cognito OAuth BFF routes', () => {
  it('starts Google authorization from a same-origin POST with PKCE, state, and nonce', async () => {
    configureOAuth();
    const response = await login(
      request('/backend/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          Origin: 'http://localhost:3000',
        },
        body: new URLSearchParams({ intent: 'ELDER', returnTo: '/family' }),
      }),
    );
    expect(response.status).toBe(303);
    const location = new URL(response.headers.get('location') ?? '');
    expect(location.origin).toBe('https://example.auth.us-west-2.amazoncognito.com');
    expect(location.pathname).toBe('/oauth2/authorize');
    expect(location.searchParams.get('identity_provider')).toBe('Google');
    expect(location.searchParams.get('code_challenge_method')).toBe('S256');
    expect(location.searchParams.get('state')).toBeTruthy();
    expect(location.searchParams.get('nonce')).toBeTruthy();
    expect(location.searchParams.get('code_verifier')).toBeNull();
    expect(cookieValue(response, oauthTransactionCookieName())).toBeTruthy();
  });

  it('only accepts a family invitation over a same-origin form POST', async () => {
    configureOAuth();
    const response = await login(
      request('/backend/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          Origin: 'http://localhost:3000',
        },
        body: new URLSearchParams({
          intent: 'FAMILY',
          invitationCode: 'family-invite-code',
          returnTo: '/onboarding/resolve',
        }),
      }),
    );
    const stored = parseOAuthTransaction(cookieValue(response, oauthTransactionCookieName()));
    expect(stored).toMatchObject({ intent: 'FAMILY', invitationCode: 'family-invite-code' });
  });

  it('rejects cross-origin OAuth initiation before creating a transaction', async () => {
    configureOAuth();
    const response = await login(
      request('/backend/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          Origin: 'https://attacker.example',
        },
        body: new URLSearchParams({ intent: 'ELDER', returnTo: '/onboarding/resolve' }),
      }),
    );

    expect(response.status).toBe(403);
    expect(cookieValue(response, oauthTransactionCookieName())).toBeUndefined();
  });

  it('logs only an allowlisted provider error identifier', async () => {
    configureOAuth();
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const query = new URLSearchParams({
      error: 'access_denied',
      error_description: 'synthetic-provider-description-secret',
      code: 'synthetic-authorization-code-secret',
      state: 'synthetic-state-secret',
    });

    const response = await callback(request(`/backend/auth/callback?${query.toString()}`));

    expect(response.status).toBe(303);
    expect(response.headers.get('location')).toBe('/sign-in?error=oauth_failed');
    expect(errorSpy).toHaveBeenCalledTimes(1);
    expect(errorSpy).toHaveBeenCalledWith('[auth] OAuth callback failed', {
      stage: 'provider_error',
      oauth_error: 'access_denied',
      error_count: 1,
    });
    const serializedLog = JSON.stringify(errorSpy.mock.calls);
    expect(serializedLog).not.toContain('synthetic-provider-description-secret');
    expect(serializedLog).not.toContain('synthetic-authorization-code-secret');
    expect(serializedLog).not.toContain('synthetic-state-secret');
  });

  it('collapses attacker-controlled provider errors to one bounded log value', async () => {
    configureOAuth();
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    await callback(
      request('/backend/auth/callback?error=attacker_chosen_log_value&error=access_denied'),
    );

    expect(errorSpy).toHaveBeenCalledWith('[auth] OAuth callback failed', {
      stage: 'provider_error',
      oauth_error: 'unrecognised',
      error_count: 2,
    });
    expect(JSON.stringify(errorSpy.mock.calls)).not.toContain('attacker_chosen_log_value');
  });

  it('logs only counts for a malformed redirect', async () => {
    configureOAuth();
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    await callback(
      request(
        '/backend/auth/callback?code=synthetic-code-one&code=synthetic-code-two&state=synthetic-state',
      ),
    );

    expect(errorSpy).toHaveBeenCalledWith('[auth] OAuth callback failed', {
      stage: 'malformed_redirect',
      code_count: 2,
      state_count: 1,
    });
    expect(JSON.stringify(errorSpy.mock.calls)).not.toContain('synthetic-code-one');
    expect(JSON.stringify(errorSpy.mock.calls)).not.toContain('synthetic-state');
  });

  it('logs only transaction booleans when state validation fails', async () => {
    configureOAuth();
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    await callback(
      request('/backend/auth/callback?code=synthetic-code-secret&state=synthetic-state-secret'),
    );

    expect(errorSpy).toHaveBeenCalledWith('[auth] OAuth callback failed', {
      stage: 'transaction',
      cookie_present: false,
      transaction_valid: false,
      state_matches: false,
    });
    const serializedLog = JSON.stringify(errorSpy.mock.calls);
    expect(serializedLog).not.toContain('synthetic-code-secret');
    expect(serializedLog).not.toContain('synthetic-state-secret');
  });

  it('exchanges a matching callback code without exposing tokens in the redirect', async () => {
    configureOAuth();
    vi.stubEnv('CORE_ONBOARDING_REDEEM_URL', 'http://127.0.0.1:8000/api/v1/onboarding/resolve');
    const transaction = createOAuthTransaction('/family', 'FAMILY');
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit): Promise<Response> =>
        Response.json({
          access_token: 'synthetic-access-token',
          expires_in: 3600,
          id_token: idToken(transaction.nonce),
        }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const response = await callback(
      request(
        `/backend/auth/callback?code=authorization-code&state=${encodeURIComponent(transaction.state)}`,
        {
          headers: {
            Cookie: `${oauthTransactionCookieName()}=${serializeOAuthTransaction(transaction)}`,
          },
        },
      ),
    );

    expect(response.status).toBe(303);
    expect(response.headers.get('location')).toBe('/family');
    expect(response.headers.get('location')).not.toContain('synthetic-access-token');
    expect(response.headers.get('location')).not.toContain('authorization-code');
    expect(cookieValue(response, 'kinsun_access_token')).toBe('synthetic-access-token');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(init?.body)).toContain('code_verifier=');
  });

  it('uses the ID token only for configured server-to-server onboarding redemption', async () => {
    configureOAuth();
    vi.stubEnv('CORE_ONBOARDING_REDEEM_URL', 'http://127.0.0.1:8000/api/v1/onboarding/resolve');
    const transaction = createOAuthTransaction(
      '/onboarding/resolve',
      'FAMILY',
      'family-invite-code',
    );
    const googleFetch = vi
      .fn(async (_input: RequestInfo | URL, _init?: RequestInit): Promise<Response> =>
        Response.json({}),
      )
      .mockResolvedValueOnce(
        Response.json({
          access_token: 'synthetic-access-token',
          expires_in: 3600,
          id_token: idToken(transaction.nonce),
        }),
      )
      .mockResolvedValueOnce(Response.json({ data: { status: 'REDEEMED' } }));
    vi.stubGlobal('fetch', googleFetch);

    const response = await callback(
      request(
        `/backend/auth/callback?code=authorization-code&state=${encodeURIComponent(transaction.state)}`,
        {
          headers: {
            Cookie: `${oauthTransactionCookieName()}=${serializeOAuthTransaction(transaction)}`,
          },
        },
      ),
    );

    expect(response.status).toBe(303);
    expect(googleFetch).toHaveBeenCalledTimes(2);
    const [target, init] = googleFetch.mock.calls[1] ?? [];
    expect(String(target)).toBe('http://127.0.0.1:8000/api/v1/onboarding/resolve');
    expect(new Headers(init?.headers).get('Authorization')).toMatch(/^Bearer .+\..+\..+$/);
    expect(new Headers(init?.headers).get('Idempotency-Key')).toBe(`oauth-${transaction.state}`);
    expect(String(init?.body)).toContain('family-invite-code');
  });

  it('does not send an ID token to a cross-origin onboarding endpoint', async () => {
    configureOAuth();
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    vi.stubEnv('CORE_ONBOARDING_REDEEM_URL', 'https://attacker.example/api/v1/onboarding/resolve');
    const transaction = createOAuthTransaction('/onboarding/resolve', 'ELDER');
    const fetchMock = vi.fn(async (): Promise<Response> =>
      Response.json({
        access_token: 'synthetic-access-token',
        expires_in: 3600,
        id_token: idToken(transaction.nonce),
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const response = await callback(
      request(
        `/backend/auth/callback?code=authorization-code&state=${encodeURIComponent(transaction.state)}`,
        {
          headers: {
            Cookie: `${oauthTransactionCookieName()}=${serializeOAuthTransaction(transaction)}`,
          },
        },
      ),
    );

    expect(response.headers.get('location')).toBe('/sign-in?error=oauth_failed');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(cookieValue(response, 'kinsun_access_token')).toBeUndefined();
    expect(errorSpy).toHaveBeenCalledWith('[auth] OAuth callback failed', {
      stage: 'core_onboarding',
    });
  });

  it('clears the local session before redirecting through Cognito logout', () => {
    configureOAuth();
    const response = logout(
      request('/backend/auth/logout', {
        method: 'POST',
        headers: { Origin: 'http://localhost:3000' },
      }),
    );
    expect(response.status).toBe(303);
    const location = new URL(response.headers.get('location') ?? '');
    expect(location.pathname).toBe('/logout');
    expect(cookieValue(response, 'kinsun_access_token')).toBe('');
    expect(cookieValue(response, oauthTransactionCookieName())).toBe('');
    expect(setCookieHeader(response)).toMatch(
      new RegExp(`${oauthTransactionCookieName()}=;.*Max-Age=0`, 'i'),
    );
  });
});
