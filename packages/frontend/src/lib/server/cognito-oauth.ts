import { normalizeAccessToken } from './auth-cookie';
import { logAuthDiagnostic } from './auth-diagnostics';
import { codeChallenge, type LoginProvider, type OAuthTransaction } from './oauth-transaction';

const REQUIRED_SCOPES = ['openid', 'email', 'profile'];
const TOKEN_EXCHANGE_TIMEOUT_MS = 10_000;
const LOGGABLE_REQUEST_ERROR_TYPES = new Set(['AbortError', 'TimeoutError', 'TypeError']);

export interface CognitoOAuthConfig {
  callbackUrl: URL;
  clientId: string;
  domain: URL;
  logoutUrl: URL;
}

export interface CognitoTokenSet {
  accessToken: string;
  expiresIn: number;
  idToken: string;
}

function safeAbsoluteUrl(rawValue: string | undefined, name: string): URL {
  if (!rawValue) throw new Error(`${name} is unavailable`);
  const value = new URL(rawValue);
  if (
    value.username ||
    value.password ||
    (value.protocol !== 'https:' && value.protocol !== 'http:')
  ) {
    throw new Error(`${name} is invalid`);
  }
  if (process.env.NODE_ENV === 'production' && value.protocol !== 'https:') {
    throw new Error(`${name} must use HTTPS in production`);
  }
  return value;
}

function clientId(): string {
  const value = process.env.COGNITO_WEB_CLIENT_ID;
  if (!value || value.length > 256 || /\s/.test(value)) {
    throw new Error('COGNITO_WEB_CLIENT_ID is unavailable');
  }
  return value;
}

function identityProviderName(provider: LoginProvider): string {
  if (provider === 'GOOGLE') return 'Google';
  if (process.env.LINE_LOGIN_ENABLED?.trim().toLowerCase() !== 'true') {
    throw new Error('LINE Login is disabled');
  }
  const value = process.env.COGNITO_LINE_PROVIDER_NAME ?? 'LINE';
  if (!/^[A-Za-z][A-Za-z0-9_-]{0,31}$/.test(value)) {
    throw new Error('COGNITO_LINE_PROVIDER_NAME is invalid');
  }
  return value;
}

export function getCognitoOAuthConfig(): CognitoOAuthConfig {
  const domain = safeAbsoluteUrl(process.env.COGNITO_OAUTH_DOMAIN, 'COGNITO_OAUTH_DOMAIN');
  const callbackUrl = safeAbsoluteUrl(process.env.COGNITO_CALLBACK_URL, 'COGNITO_CALLBACK_URL');
  const logoutUrl = safeAbsoluteUrl(process.env.COGNITO_LOGOUT_URL, 'COGNITO_LOGOUT_URL');
  const frontendOrigin = safeAbsoluteUrl(process.env.FRONTEND_ORIGIN, 'FRONTEND_ORIGIN');

  if (callbackUrl.origin !== frontendOrigin.origin || logoutUrl.origin !== frontendOrigin.origin) {
    throw new Error('Cognito callback and logout URLs must use FRONTEND_ORIGIN');
  }
  return { callbackUrl, clientId: clientId(), domain, logoutUrl };
}

function cognitoEndpoint(config: CognitoOAuthConfig, pathname: string): URL {
  const endpoint = new URL(pathname, config.domain);
  if (endpoint.origin !== config.domain.origin) throw new Error('Invalid Cognito endpoint');
  return endpoint;
}

export function buildCognitoAuthorizationUrl(
  config: CognitoOAuthConfig,
  transaction: OAuthTransaction,
): URL {
  const target = cognitoEndpoint(config, '/oauth2/authorize');
  target.searchParams.set('client_id', config.clientId);
  target.searchParams.set('code_challenge', codeChallenge(transaction.codeVerifier));
  target.searchParams.set('code_challenge_method', 'S256');
  target.searchParams.set('identity_provider', identityProviderName(transaction.provider));
  target.searchParams.set('nonce', transaction.nonce);
  target.searchParams.set('redirect_uri', config.callbackUrl.toString());
  target.searchParams.set('response_type', 'code');
  target.searchParams.set('scope', REQUIRED_SCOPES.join(' '));
  target.searchParams.set('state', transaction.state);
  return target;
}

/** Backward-compatible wrapper for callers that construct a Google transaction. */
export function buildGoogleAuthorizationUrl(
  config: CognitoOAuthConfig,
  transaction: OAuthTransaction,
): URL {
  if (transaction.provider !== 'GOOGLE') throw new Error('Google transaction required');
  return buildCognitoAuthorizationUrl(config, transaction);
}

function decodeIdTokenNonce(idToken: string): string | null {
  const parts = idToken.split('.');
  if (parts.length !== 3 || !parts[1]) return null;
  try {
    const payload = JSON.parse(Buffer.from(parts[1], 'base64url').toString('utf8')) as {
      nonce?: unknown;
    };
    return typeof payload.nonce === 'string' ? payload.nonce : null;
  } catch {
    return null;
  }
}

function validExpiresIn(value: unknown): number | null {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 60 || value > 86_400) {
    return null;
  }
  return value;
}

function safeRequestErrorType(error: unknown): string {
  const value = error instanceof Error ? error.name : '';
  return LOGGABLE_REQUEST_ERROR_TYPES.has(value) ? value : 'UnknownError';
}

/** Exchanges a single authorization code. Tokens stay server-side and are never logged. */
export async function exchangeAuthorizationCode(
  config: CognitoOAuthConfig,
  code: string,
  transaction: OAuthTransaction,
): Promise<CognitoTokenSet> {
  if (!code || code.length > 4_096 || /\s/.test(code)) {
    throw new Error('Invalid authorization code');
  }

  const body = new URLSearchParams({
    client_id: config.clientId,
    code,
    code_verifier: transaction.codeVerifier,
    grant_type: 'authorization_code',
    redirect_uri: config.callbackUrl.toString(),
  });
  let response: Response;
  try {
    response = await fetch(cognitoEndpoint(config, '/oauth2/token'), {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/x-www-form-urlencoded' },
      body,
      cache: 'no-store',
      redirect: 'error',
      signal: AbortSignal.timeout(TOKEN_EXCHANGE_TIMEOUT_MS),
    });
  } catch (error) {
    logAuthDiagnostic('Cognito token exchange request failed', {
      error_type: safeRequestErrorType(error),
    });
    throw new Error('Cognito token exchange failed');
  }
  if (!response.ok) {
    logAuthDiagnostic('Cognito token exchange rejected', { status: response.status });
    throw new Error('Cognito token exchange failed');
  }

  const payload = (await response.json().catch(() => null)) as {
    access_token?: unknown;
    expires_in?: unknown;
    id_token?: unknown;
  } | null;
  if (!payload || typeof payload.id_token !== 'string') {
    throw new Error('Invalid Cognito token response');
  }
  const accessToken = normalizeAccessToken(payload.access_token);
  const expiresIn = validExpiresIn(payload.expires_in);
  const nonce = decodeIdTokenNonce(payload.id_token);
  if (!accessToken || !expiresIn || nonce !== transaction.nonce) {
    logAuthDiagnostic('Cognito token response validation failed', {
      access_token_valid: Boolean(accessToken),
      expires_in_valid: Boolean(expiresIn),
      nonce_present: nonce !== null,
      nonce_matches: nonce === transaction.nonce,
    });
    throw new Error('Invalid Cognito token response');
  }
  return { accessToken, expiresIn, idToken: payload.id_token };
}

export function buildCognitoLogoutUrl(config: CognitoOAuthConfig): URL {
  const target = cognitoEndpoint(config, '/logout');
  target.searchParams.set('client_id', config.clientId);
  target.searchParams.set('logout_uri', config.logoutUrl.toString());
  return target;
}
