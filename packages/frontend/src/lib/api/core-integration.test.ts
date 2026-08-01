import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiRequestError, apiFetch, type ApiConfig } from './client';
import { createTextSession, runCompanionTurn } from './companion';
import { activeBasicVoiceConsent, listConsents } from './consent';

const config: ApiConfig = {
  apiBaseUrl: '/backend/core/',
};

function success<T>(data: T): Response {
  return new Response(
    JSON.stringify({
      data,
      meta: {
        correlation_id: 'correlation-1',
        timestamp: '2026-08-01T00:00:00Z',
        schema_version: '1.0',
      },
    }),
    { status: 200, headers: { 'Content-Type': 'application/json' } },
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('Core API integration clients', () => {
  it('unwraps SuccessEnvelope and leaves credentials to the same-origin BFF', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      success({ value: 7 }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(
      apiFetch<{ value: number }>(config, '/api/v1/example', {
        headers: { Authorization: 'Bearer browser-readable-token' },
      }),
    ).resolves.toEqual({ value: 7 });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/backend/core/api/v1/example');
    expect(new Headers(init?.headers).has('Authorization')).toBe(false);
    expect(init?.credentials).toBe('same-origin');
  });

  it('keeps Core reason_code without exposing arbitrary response text', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              error: {
                code: 'service_unavailable',
                message: 'Agent runtime is unavailable',
                reason_code: 'SERVICE_UNAVAILABLE',
                retryable: true,
              },
            }),
            { status: 503, headers: { 'Content-Type': 'application/json' } },
          ),
      ),
    );

    const error = await apiFetch(config, '/api/v1/example').catch((caught) => caught);
    expect(error).toBeInstanceOf(ApiRequestError);
    expect(error).toMatchObject({
      status: 503,
      reasonCode: 'SERVICE_UNAVAILABLE',
      retryable: true,
    });
  });

  it('reads BASIC_VOICE consent from the current snake_case Core contract', async () => {
    const consent = {
      consent_id: '81000000-0000-4000-8000-000000000001',
      purpose_code: 'BASIC_VOICE' as const,
      consent_version: 1,
      status: 'GRANTED' as const,
      policy_version: 'demo-consent-v1',
      effective_at: '2026-08-01T00:00:00Z',
      expires_at: null,
      revoked_at: null,
      affected_capabilities: ['voice_session'],
      deletion_request_id: null,
    };
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      success({ items: [consent] }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const items = await listConsents(config, '40000000-0000-4000-8000-000000000001');

    expect(activeBasicVoiceConsent(items)).toEqual(consent);
    expect(fetchMock.mock.calls[0][0]).toBe(
      '/backend/core/api/v1/elders/40000000-0000-4000-8000-000000000001/consents',
    );
  });

  it('creates a text session before sending a companion turn', async () => {
    vi.stubGlobal('crypto', { randomUUID: () => '00000000-0000-4000-8000-000000000001' });
    const fetchMock = vi
      .fn(async (_input: RequestInfo | URL, _init?: RequestInit): Promise<Response> => success({}))
      .mockResolvedValueOnce(
        success({
          session_id: '51000000-0000-4000-8000-000000000001',
          elder_id: '40000000-0000-4000-8000-000000000001',
          state: 'CREATED',
          language_route: 'ZH_TW',
          consent_version: 1,
          policy_version: 'demo-consent-v1',
          transport_status: 'NOT_CONFIGURED',
        }),
      )
      .mockResolvedValueOnce(
        success({
          session_id: '51000000-0000-4000-8000-000000000001',
          agent_run_id: '52000000-0000-4000-8000-000000000001',
          trace_id: 'trace-1',
          context_manifest_id: 'context-1',
          reply_text: '安全回覆',
          reply_language: 'zh-TW',
          result_status: 'SUCCESS',
          safety_decision: 'ALLOW',
          risk_level: 'LOW',
          reason_codes: ['ALLOW'],
          session_state: 'COMPLETED',
          transport_status: 'TEXT_ONLY',
          model_route: 'mock',
        }),
      );
    vi.stubGlobal('fetch', fetchMock);

    const session = await createTextSession(config, '40000000-0000-4000-8000-000000000001');
    const turn = await runCompanionTurn(config, session.session_id, '合成測試文字');

    expect(turn.reply_text).toBe('安全回覆');
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      '/backend/core/api/v1/elders/40000000-0000-4000-8000-000000000001/voice-sessions',
      '/backend/core/api/v1/voice-sessions/51000000-0000-4000-8000-000000000001/companion-turns',
    ]);
    const turnBody = fetchMock.mock.calls[1]?.[1]?.body;
    expect(typeof turnBody).toBe('string');
    const turnRequest = JSON.parse(String(turnBody));
    expect(turnRequest).toEqual({ input_text: '合成測試文字' });
    expect(turnRequest).not.toHaveProperty('actor_id');
    expect(turnRequest).not.toHaveProperty('tenant_id');
  });
});
