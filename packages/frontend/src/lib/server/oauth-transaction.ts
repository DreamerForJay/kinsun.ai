import { createHash, createHmac, randomBytes, timingSafeEqual } from 'node:crypto';

const DEVELOPMENT_OAUTH_TRANSACTION_COOKIE = 'kinsun_oauth_transaction';
const PRODUCTION_OAUTH_TRANSACTION_COOKIE = '__Host-kinsun_oauth_transaction';
const TRANSACTION_TTL_SECONDS = 10 * 60;
const ALLOWED_RETURN_PATHS = new Set([
  '/',
  '/consent',
  '/dashboard',
  '/family',
  '/onboarding/resolve',
  '/sign-in',
]);

export interface OAuthTransaction {
  codeVerifier: string;
  createdAt: number;
  intent: OnboardingIntent;
  invitationCode?: string;
  nonce: string;
  returnTo: string;
  state: string;
}

export type OnboardingIntent = 'ELDER' | 'FAMILY' | 'STAFF';

function base64Url(value: Buffer): string {
  return value.toString('base64url');
}

function randomValue(): string {
  return base64Url(randomBytes(32));
}

function signingSecret(): string {
  const secret = process.env.COGNITO_OAUTH_TRANSACTION_SECRET;
  if (!secret || secret.length < 32) {
    throw new Error('OAuth transaction signing secret is unavailable');
  }
  return secret;
}

function signature(payload: string): string {
  return createHmac('sha256', signingSecret()).update(payload).digest('base64url');
}

function safeEqual(left: string, right: string): boolean {
  const leftBuffer = Buffer.from(left);
  const rightBuffer = Buffer.from(right);
  return leftBuffer.length === rightBuffer.length && timingSafeEqual(leftBuffer, rightBuffer);
}

export function strictRelativeReturnTo(value: string | null): string | null {
  if (value === null || value === '') return '/onboarding/resolve';
  if (!value.startsWith('/') || value.startsWith('//') || value.includes('\\')) return null;

  try {
    const parsed = new URL(value, 'https://frontend.invalid');
    if (parsed.origin !== 'https://frontend.invalid') return null;
    if (!ALLOWED_RETURN_PATHS.has(parsed.pathname) || parsed.search || parsed.hash) return null;
    return parsed.pathname;
  } catch {
    return null;
  }
}

export function onboardingIntent(value: unknown): OnboardingIntent | null {
  return value === 'ELDER' || value === 'FAMILY' || value === 'STAFF' ? value : null;
}

export function normalizeInvitationCode(value: unknown): string | undefined | null {
  if (value === undefined || value === null || value === '') return undefined;
  if (typeof value !== 'string') return null;
  const code = value.trim();
  if (code.length < 16 || code.length > 24 || /[\r\n\0]/.test(code)) return null;
  return code;
}

export function createOAuthTransaction(
  returnTo: string,
  intent: OnboardingIntent,
  invitationCode?: string,
): OAuthTransaction {
  return {
    codeVerifier: randomValue(),
    createdAt: Date.now(),
    intent,
    ...(invitationCode ? { invitationCode } : {}),
    nonce: randomValue(),
    returnTo,
    state: randomValue(),
  };
}

export function codeChallenge(codeVerifier: string): string {
  return createHash('sha256').update(codeVerifier).digest('base64url');
}

export function serializeOAuthTransaction(transaction: OAuthTransaction): string {
  const payload = base64Url(Buffer.from(JSON.stringify(transaction), 'utf8'));
  return `${payload}.${signature(payload)}`;
}

export function parseOAuthTransaction(value: string | undefined): OAuthTransaction | null {
  if (!value) return null;
  const [payload, providedSignature, ...extra] = value.split('.');
  if (!payload || !providedSignature || extra.length > 0) return null;

  try {
    if (!safeEqual(signature(payload), providedSignature)) return null;
    const parsed = JSON.parse(
      Buffer.from(payload, 'base64url').toString('utf8'),
    ) as Partial<OAuthTransaction>;
    if (
      typeof parsed.codeVerifier !== 'string' ||
      onboardingIntent(parsed.intent) === null ||
      typeof parsed.nonce !== 'string' ||
      typeof parsed.returnTo !== 'string' ||
      typeof parsed.state !== 'string' ||
      typeof parsed.createdAt !== 'number' ||
      !Number.isSafeInteger(parsed.createdAt) ||
      parsed.createdAt > Date.now() ||
      Date.now() - parsed.createdAt > TRANSACTION_TTL_SECONDS * 1000 ||
      !strictRelativeReturnTo(parsed.returnTo) ||
      parsed.codeVerifier.length < 43 ||
      parsed.state.length < 32 ||
      parsed.nonce.length < 32
    ) {
      return null;
    }
    const invitationCode = normalizeInvitationCode(parsed.invitationCode);
    if (parsed.invitationCode !== undefined && invitationCode === null) return null;
    return {
      ...(parsed as OAuthTransaction),
      ...(invitationCode ? { invitationCode } : {}),
    };
  } catch {
    return null;
  }
}

export function stateMatches(transaction: OAuthTransaction, suppliedState: string | null): boolean {
  return suppliedState !== null && safeEqual(transaction.state, suppliedState);
}

export function oauthTransactionCookieName(): string {
  return process.env.NODE_ENV === 'production'
    ? PRODUCTION_OAUTH_TRANSACTION_COOKIE
    : DEVELOPMENT_OAUTH_TRANSACTION_COOKIE;
}

export function oauthTransactionCookieOptions() {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax' as const,
    path: '/',
    maxAge: TRANSACTION_TTL_SECONDS,
  };
}
