/**
 * Deterministic browser regression for login -> callback -> logout -> login -> callback.
 *
 * This deliberately mocks Cognito at its HTTP boundary instead of using /dev-login or
 * injecting a browser token. The real BFF routes still create and validate the signed
 * OAuth transaction, exchange both authorization codes with PKCE, set HttpOnly access
 * cookies, and redirect through the configured Cognito logout endpoint.
 *
 * The script copies the small frontend project into a temporary directory before
 * starting Next dev. That gives the test its own .next lock and lets it run while a
 * developer already has this checkout open on port 3000.
 */

import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { once } from 'node:events';
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  rmSync,
  symlinkSync,
} from 'node:fs';
import { createServer } from 'node:http';
import { basename, dirname, join, resolve } from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const require = createRequire(import.meta.url);
const SCRIPT_DIRECTORY = dirname(fileURLToPath(import.meta.url));
const FRONTEND_DIRECTORY = resolve(SCRIPT_DIRECTORY, '..');
const REPOSITORY_DIRECTORY = resolve(FRONTEND_DIRECTORY, '../..');
const WORKSPACE_DIRECTORY = resolve(REPOSITORY_DIRECTORY, '..');
const E2E_TEMP_DIRECTORY = join(WORKSPACE_DIRECTORY, '.tmp');
const REPOSITORY_NODE_MODULES = join(REPOSITORY_DIRECTORY, 'node_modules');
const NEXT_CLI = require.resolve('next/dist/bin/next');

const FRONTEND_PORT = Number(process.env.AUTH_RELOGIN_E2E_FRONTEND_PORT ?? '34179');
assert.ok(
  Number.isSafeInteger(FRONTEND_PORT) && FRONTEND_PORT >= 1024 && FRONTEND_PORT <= 65535,
  'AUTH_RELOGIN_E2E_FRONTEND_PORT must be an unprivileged TCP port',
);

const FRONTEND_ORIGIN = `http://127.0.0.1:${FRONTEND_PORT}`;
const CALLBACK_URL = `${FRONTEND_ORIGIN}/backend/auth/callback`;
const LOGOUT_URL = `${FRONTEND_ORIGIN}/sign-in`;
const CLIENT_ID = 'synthetic-browser-e2e-client';
const ACCESS_COOKIE = 'kinsun_access_token';
const TRANSACTION_COOKIE = 'kinsun_oauth_transaction';
const SESSION_STORAGE_KEYS = [
  'elderly_care_id_token',
  'elderly_care_voice_ws_token',
  'elderly_care_elder_id',
  'elderly_care_caregiver_id',
];
const UNRELATED_PREFERENCE_KEY = 'synthetic_unrelated_preference';

function delay(milliseconds) {
  return new Promise((resolveDelay) => setTimeout(resolveDelay, milliseconds));
}

function writeJson(response, status, payload) {
  response.writeHead(status, {
    'Cache-Control': 'no-store',
    'Content-Type': 'application/json; charset=utf-8',
  });
  response.end(JSON.stringify(payload));
}

async function requestBody(request) {
  let body = '';
  for await (const chunk of request) {
    body += chunk.toString('utf8');
    assert.ok(body.length <= 16_384, 'mock Cognito request body exceeded its test limit');
  }
  return body;
}

function syntheticIdToken(nonce) {
  const header = Buffer.from(JSON.stringify({ alg: 'RS256', typ: 'JWT' })).toString('base64url');
  const payload = Buffer.from(
    JSON.stringify({
      aud: CLIENT_ID,
      email: 'synthetic.staff@example.invalid',
      email_verified: true,
      name: 'Synthetic Staff',
      nonce,
      token_use: 'id',
    }),
  ).toString('base64url');
  return `${header}.${payload}.synthetic-signature`;
}

async function startMockCognito() {
  const grants = new Map();
  const observations = {
    authorizations: [],
    errors: [],
    logouts: [],
    tokenExchanges: [],
  };
  let providerSessionActive = false;

  const server = createServer((request, response) => {
    void (async () => {
      const url = new URL(request.url ?? '/', 'http://mock-cognito.invalid');

      if (request.method === 'GET' && url.pathname === '/oauth2/authorize') {
        assert.equal(url.searchParams.get('client_id'), CLIENT_ID);
        assert.equal(url.searchParams.get('redirect_uri'), CALLBACK_URL);
        assert.equal(url.searchParams.get('response_type'), 'code');
        assert.equal(url.searchParams.get('identity_provider'), 'Google');
        assert.equal(url.searchParams.get('code_challenge_method'), 'S256');
        assert.deepEqual(
          new Set((url.searchParams.get('scope') ?? '').split(' ')),
          new Set(['openid', 'email', 'profile']),
        );

        const state = url.searchParams.get('state');
        const nonce = url.searchParams.get('nonce');
        const codeChallenge = url.searchParams.get('code_challenge');
        assert.ok(state && state.length >= 32, 'authorization state was missing or too short');
        assert.ok(nonce && nonce.length >= 32, 'authorization nonce was missing or too short');
        assert.ok(codeChallenge, 'PKCE code challenge was missing');

        const cycle = observations.authorizations.length + 1;
        const code = `synthetic-authorization-code-${cycle}`;
        assert.equal(providerSessionActive, false, 'a prior mock provider session survived logout');
        providerSessionActive = true;
        grants.set(code, { codeChallenge, cycle, nonce });
        observations.authorizations.push({ code, codeChallenge, nonce, state });

        const callback = new URL(CALLBACK_URL);
        callback.searchParams.set('code', code);
        callback.searchParams.set('state', state);
        response.writeHead(303, { 'Cache-Control': 'no-store', Location: callback.toString() });
        response.end();
        return;
      }

      if (request.method === 'POST' && url.pathname === '/oauth2/token') {
        assert.match(
          request.headers['content-type'] ?? '',
          /^application\/x-www-form-urlencoded(?:;|$)/i,
        );
        const form = new URLSearchParams(await requestBody(request));
        assert.equal(form.get('client_id'), CLIENT_ID);
        assert.equal(form.get('grant_type'), 'authorization_code');
        assert.equal(form.get('redirect_uri'), CALLBACK_URL);

        const code = form.get('code');
        const verifier = form.get('code_verifier');
        assert.ok(code, 'authorization code was missing from the token exchange');
        assert.ok(verifier, 'PKCE verifier was missing from the token exchange');
        const grant = grants.get(code);
        assert.ok(grant, 'authorization code was unknown or reused');
        assert.equal(
          createHash('sha256').update(verifier).digest('base64url'),
          grant.codeChallenge,
          'PKCE verifier did not match the authorization request',
        );
        grants.delete(code);
        observations.tokenExchanges.push({ code, cycle: grant.cycle });

        writeJson(response, 200, {
          access_token: `synthetic-access-token-${grant.cycle}`,
          expires_in: 3600,
          id_token: syntheticIdToken(grant.nonce),
          token_type: 'Bearer',
        });
        return;
      }

      if (request.method === 'GET' && url.pathname === '/logout') {
        assert.equal(url.searchParams.get('client_id'), CLIENT_ID);
        assert.equal(url.searchParams.get('logout_uri'), LOGOUT_URL);
        assert.equal(providerSessionActive, true, 'mock Cognito logout had no active session');
        providerSessionActive = false;
        observations.logouts.push({ completed: true });
        response.writeHead(303, { 'Cache-Control': 'no-store', Location: LOGOUT_URL });
        response.end();
        return;
      }

      writeJson(response, 404, { error: 'not_found' });
    })().catch((error) => {
      observations.errors.push(error instanceof Error ? error.message : 'Unknown mock error');
      if (!response.headersSent) writeJson(response, 400, { error: 'invalid_request' });
      else response.end();
    });
  });

  await new Promise((resolveListen, rejectListen) => {
    server.once('error', rejectListen);
    server.listen(0, resolveListen);
  });
  const address = server.address();
  assert.ok(address && typeof address !== 'string', 'mock Cognito did not bind a TCP port');

  return {
    observations,
    origin: `http://localhost:${address.port}`,
    async close() {
      await new Promise((resolveClose, rejectClose) => {
        server.close((error) => (error ? rejectClose(error) : resolveClose()));
        server.closeAllConnections?.();
      });
    },
    unconsumedGrantCount: () => grants.size,
  };
}

async function assertFrontendPortAvailable() {
  const probe = createServer();
  await new Promise((resolveListen, rejectListen) => {
    probe.once('error', rejectListen);
    probe.listen(FRONTEND_PORT, '127.0.0.1', resolveListen);
  });
  await new Promise((resolveClose, rejectClose) => {
    probe.close((error) => (error ? rejectClose(error) : resolveClose()));
  });
}

function createIsolatedFrontendCopy() {
  mkdirSync(E2E_TEMP_DIRECTORY, { recursive: true });
  const temporaryRoot = mkdtempSync(join(E2E_TEMP_DIRECTORY, 'kinsun-auth-relogin-e2e-'));
  try {
    for (const directory of ['public', 'src']) {
      copyDirectory(join(FRONTEND_DIRECTORY, directory), join(temporaryRoot, directory));
    }
    for (const file of ['next-env.d.ts', 'next.config.mjs', 'package.json', 'tsconfig.json']) {
      copyFileSync(join(FRONTEND_DIRECTORY, file), join(temporaryRoot, file));
    }
    assert.ok(existsSync(REPOSITORY_NODE_MODULES), 'repository node_modules is unavailable');
    symlinkSync(
      REPOSITORY_NODE_MODULES,
      join(temporaryRoot, 'node_modules'),
      process.platform === 'win32' ? 'junction' : 'dir',
    );
    return temporaryRoot;
  } catch (error) {
    removeIsolatedFrontendCopy(temporaryRoot);
    throw error;
  }
}

function copyDirectory(source, destination) {
  mkdirSync(destination, { recursive: true });
  for (const entry of readdirSync(source, { withFileTypes: true })) {
    const sourcePath = join(source, entry.name);
    const destinationPath = join(destination, entry.name);
    if (entry.isDirectory()) copyDirectory(sourcePath, destinationPath);
    else if (entry.isFile()) copyFileSync(sourcePath, destinationPath);
    else throw new Error(`unsupported entry in isolated frontend copy: ${entry.name}`);
  }
}

function removeIsolatedFrontendCopy(temporaryRoot) {
  const resolvedTemporaryRoot = resolve(temporaryRoot);
  assert.equal(
    dirname(resolvedTemporaryRoot),
    resolve(E2E_TEMP_DIRECTORY),
    'refusing to remove a non-E2E-temp path',
  );
  assert.match(
    basename(resolvedTemporaryRoot),
    /^kinsun-auth-relogin-e2e-/,
    'refusing to remove an unexpected temp directory',
  );
  rmSync(resolvedTemporaryRoot, { force: true, recursive: true });
}

function startNext(temporaryRoot, cognitoOrigin) {
  const environment = {
    ...process.env,
    COGNITO_CALLBACK_URL: CALLBACK_URL,
    COGNITO_LOGOUT_URL: LOGOUT_URL,
    COGNITO_OAUTH_DOMAIN: cognitoOrigin,
    COGNITO_OAUTH_TRANSACTION_SECRET: 'synthetic-e2e-transaction-secret-at-least-32-characters',
    COGNITO_WEB_CLIENT_ID: CLIENT_ID,
    CORE_API_INTERNAL_URL: 'http://127.0.0.1:9',
    CORE_ONBOARDING_REDEEM_URL: '',
    FRONTEND_ORIGIN,
    NODE_ENV: 'development',
  };
  // The auth test neither needs nor should inherit deploy credentials.
  delete environment.AWS_ACCESS_KEY_ID;
  delete environment.AWS_SECRET_ACCESS_KEY;
  delete environment.AWS_SESSION_TOKEN;

  const child = spawn(
    process.execPath,
    [NEXT_CLI, 'dev', '--hostname', '127.0.0.1', '--port', String(FRONTEND_PORT)],
    {
      cwd: temporaryRoot,
      env: environment,
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    },
  );
  let output = '';
  const capture = (chunk) => {
    output = `${output}${chunk.toString('utf8')}`.slice(-20_000);
  };
  child.stdout.on('data', capture);
  child.stderr.on('data', capture);
  return { child, output: () => output };
}

async function waitForFrontend(nextProcess) {
  const deadline = Date.now() + 90_000;
  while (Date.now() < deadline) {
    if (nextProcess.child.exitCode !== null) {
      throw new Error(`isolated Next server exited early\n${nextProcess.output()}`);
    }
    try {
      const response = await fetch(`${FRONTEND_ORIGIN}/health`, {
        cache: 'no-store',
        signal: AbortSignal.timeout(2_000),
      });
      if (response.ok) return;
    } catch {
      // Compilation and socket startup are expected to race the first probes.
    }
    await delay(250);
  }
  throw new Error(`isolated Next server did not become healthy\n${nextProcess.output()}`);
}

async function stopNext(nextProcess) {
  if (!nextProcess || nextProcess.child.exitCode !== null) return;
  nextProcess.child.kill('SIGTERM');
  await Promise.race([once(nextProcess.child, 'exit'), delay(5_000)]);
  if (nextProcess.child.exitCode === null) {
    nextProcess.child.kill('SIGKILL');
    await Promise.race([once(nextProcess.child, 'exit'), delay(2_000)]);
  }
}

function cookie(cookies, name) {
  return cookies.find((candidate) => candidate.name === name);
}

function assertCleanDestination(page, pathname) {
  const location = new URL(page.url());
  assert.equal(location.origin, FRONTEND_ORIGIN);
  assert.equal(location.pathname, pathname);
  assert.equal(location.search, '', 'final application URL retained OAuth query parameters');
  assert.equal(location.hash, '');
}

async function completeStaffLogin(page, context, cycle) {
  await page.goto(`${FRONTEND_ORIGIN}/staff/sign-in`, {
    timeout: 90_000,
    waitUntil: 'domcontentloaded',
  });
  const destination = page.waitForURL(
    (url) => url.origin === FRONTEND_ORIGIN && url.pathname === '/onboarding/resolve',
    { timeout: 90_000, waitUntil: 'domcontentloaded' },
  );
  await page.locator('form[action="/backend/auth/login"] button[type="submit"]').click();
  await destination;
  assertCleanDestination(page, '/onboarding/resolve');

  const cookies = await context.cookies(FRONTEND_ORIGIN);
  const accessCookie = cookie(cookies, ACCESS_COOKIE);
  assert.ok(accessCookie, `cycle ${cycle} did not set the access cookie`);
  assert.equal(accessCookie.value, `synthetic-access-token-${cycle}`);
  assert.equal(accessCookie.httpOnly, true);
  assert.equal(accessCookie.sameSite, 'Lax');
  assert.equal(
    cookie(cookies, TRANSACTION_COOKIE),
    undefined,
    `cycle ${cycle} retained the OAuth transaction cookie after callback`,
  );
}

async function runBrowserFlow(provider) {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ serviceWorkers: 'block' });
  const page = await context.newPage();
  const credentialQueryViolations = [];

  page.on('request', (request) => {
    const url = new URL(request.url());
    for (const key of ['access_token', 'id_token']) {
      if (url.searchParams.has(key)) credentialQueryViolations.push({ key, path: url.pathname });
    }
  });
  await context.route('**/backend/core/**', async (route) => {
    await route.fulfill({
      body: JSON.stringify({ error: { code: 'not_authenticated', message: 'Synthetic E2E' } }),
      contentType: 'application/json',
      status: 401,
    });
  });

  try {
    await completeStaffLogin(page, context, 1);
    assert.equal(provider.observations.authorizations.length, 1);
    assert.equal(provider.observations.tokenExchanges.length, 1);

    await page.evaluate(
      ({ preferenceKey, sessionKeys }) => {
        for (const key of sessionKeys) window.localStorage.setItem(key, `synthetic-${key}`);
        window.localStorage.setItem(preferenceKey, 'preserve-me');
      },
      { preferenceKey: UNRELATED_PREFERENCE_KEY, sessionKeys: SESSION_STORAGE_KEYS },
    );

    const signedOut = page.waitForURL(
      (url) => url.origin === FRONTEND_ORIGIN && url.pathname === '/sign-in',
      { timeout: 90_000, waitUntil: 'domcontentloaded' },
    );
    await page.locator('form[action="/backend/auth/logout"] button[type="submit"]').click();
    await signedOut;
    assertCleanDestination(page, '/sign-in');
    await page.waitForFunction(
      ({ preferenceKey, sessionKeys }) =>
        sessionKeys.every((key) => window.localStorage.getItem(key) === null) &&
        window.localStorage.getItem(preferenceKey) === 'preserve-me',
      { preferenceKey: UNRELATED_PREFERENCE_KEY, sessionKeys: SESSION_STORAGE_KEYS },
      { timeout: 30_000 },
    );

    const signedOutCookies = await context.cookies(FRONTEND_ORIGIN);
    assert.equal(cookie(signedOutCookies, ACCESS_COOKIE), undefined);
    assert.equal(cookie(signedOutCookies, TRANSACTION_COOKIE), undefined);
    assert.equal(provider.observations.logouts.length, 1);

    await completeStaffLogin(page, context, 2);
    assert.equal(provider.observations.authorizations.length, 2);
    assert.equal(provider.observations.tokenExchanges.length, 2);
    assert.equal(provider.observations.logouts.length, 1);
    assert.notEqual(
      provider.observations.authorizations[0].state,
      provider.observations.authorizations[1].state,
      'the second login reused the first OAuth state',
    );
    assert.notEqual(
      provider.observations.authorizations[0].nonce,
      provider.observations.authorizations[1].nonce,
      'the second login reused the first OIDC nonce',
    );
    assert.notEqual(
      provider.observations.authorizations[0].codeChallenge,
      provider.observations.authorizations[1].codeChallenge,
      'the second login reused the first PKCE challenge',
    );
    assert.deepEqual(
      provider.observations.tokenExchanges.map(({ cycle }) => cycle),
      [1, 2],
    );
    assert.equal(provider.unconsumedGrantCount(), 0);
    assert.deepEqual(provider.observations.errors, []);
    assert.deepEqual(credentialQueryViolations, []);

    const finalBrowserState = await page.evaluate(
      ({ preferenceKey, sessionKeys }) => ({
        preference: window.localStorage.getItem(preferenceKey),
        sessionValues: sessionKeys.map((key) => window.localStorage.getItem(key)),
      }),
      { preferenceKey: UNRELATED_PREFERENCE_KEY, sessionKeys: SESSION_STORAGE_KEYS },
    );
    assert.equal(finalBrowserState.preference, 'preserve-me');
    assert.deepEqual(finalBrowserState.sessionValues, [null, null, null, null]);
  } finally {
    await context.close();
    await browser.close();
  }
}

let provider;
let nextProcess;
let temporaryRoot;
try {
  await assertFrontendPortAvailable();
  provider = await startMockCognito();
  temporaryRoot = createIsolatedFrontendCopy();
  nextProcess = startNext(temporaryRoot, provider.origin);
  await waitForFrontend(nextProcess);
  await runBrowserFlow(provider);
  console.log('PASS auth relogin E2E: two OAuth callbacks succeeded with an intervening logout');
} catch (error) {
  if (nextProcess) {
    console.error(`isolated Next output:\n${nextProcess.output()}`);
  }
  throw error;
} finally {
  await stopNext(nextProcess);
  if (provider) await provider.close();
  if (temporaryRoot) removeIsolatedFrontendCopy(temporaryRoot);
}
