import { afterEach, describe, expect, it, vi } from 'vitest';
import { GET } from './route';

describe('frontend health route', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('returns a minimal, non-cacheable liveness response', async () => {
    const response = GET();

    expect(response.status).toBe(200);
    expect(response.headers.get('cache-control')).toBe('no-store');
    expect(response.headers.get('x-content-type-options')).toBe('nosniff');
    await expect(response.json()).resolves.toEqual({ status: 'ok' });
  });

  it('never exposes server-side configuration or credentials', async () => {
    const marker = 'must-not-appear-in-health-response';
    vi.stubEnv('COGNITO_OAUTH_TRANSACTION_SECRET', marker);
    vi.stubEnv('CORE_API_INTERNAL_URL', `https://${marker}.invalid`);

    const body = await GET().text();

    expect(body).toBe('{"status":"ok"}');
    expect(body).not.toContain(marker);
  });
});
