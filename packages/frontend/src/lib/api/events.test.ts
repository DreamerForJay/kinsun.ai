import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ApiConfig } from './client';
import { summariseNeedsReview } from './events';

const config: ApiConfig = { apiBaseUrl: '/backend/core/' };

function success<T>(data: T): Response {
  return new Response(
    JSON.stringify({
      data,
      meta: {
        correlation_id: 'correlation-1',
        timestamp: '2026-08-02T00:00:00Z',
        schema_version: '1.0',
      },
    }),
    { status: 200, headers: { 'Content-Type': 'application/json' } },
  );
}

function event(overrides: Record<string, unknown> = {}) {
  return {
    event_id: 'event-1',
    elder_id: 'elder-1',
    event_type: 'MEAL',
    event_time: '2026-08-01T08:00:00Z',
    status: 'NEEDS_REVIEW',
    structured_payload: { summary: '早餐吃了粥' },
    evidence_refs: ['utterance-1'],
    confidence_band: 'LOW',
    version: 1,
    consent_version: 1,
    created_at: '2026-08-01T08:00:00Z',
    updated_at: '2026-08-01T08:00:00Z',
    ...overrides,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('summariseNeedsReview', () => {
  it('asks Core for the review queue rather than filtering a page in the browser', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      success({ items: [], next_cursor: null, has_more: false }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await summariseNeedsReview(config, 'elder-1');

    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('status=NEEDS_REVIEW');
  });

  it('counts the queue and breaks it down by confidence band', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        success({
          items: [
            event({ event_id: 'a', confidence_band: 'LOW' }),
            event({ event_id: 'b', confidence_band: 'LOW' }),
            event({ event_id: 'c', confidence_band: 'MEDIUM' }),
          ],
          next_cursor: null,
          has_more: false,
        }),
      ),
    );

    const summary = await summariseNeedsReview(config, 'elder-1');

    expect(summary.count).toBe(3);
    expect(summary.byConfidence).toEqual({ LOW: 2, MEDIUM: 1, HIGH: 0 });
    expect(summary.atLeast).toBe(false);
  });

  /* Pagination is opaque-cursor only and exposes no total (AGENTS.md §8.1), so
     a further page means the number shown is a floor. Presenting it as exact
     would state an unknown as a fact (§4). */
  it('marks the count as a lower bound when Core has another page', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        success({ items: [event()], next_cursor: 'opaque-cursor', has_more: true }),
      ),
    );

    const summary = await summariseNeedsReview(config, 'elder-1');

    expect(summary.count).toBe(1);
    expect(summary.atLeast).toBe(true);
  });

  it('reports an empty queue without inventing a band', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => success({ items: [], next_cursor: null, has_more: false })),
    );

    const summary = await summariseNeedsReview(config, 'elder-1');

    expect(summary.count).toBe(0);
    expect(summary.byConfidence).toEqual({ LOW: 0, MEDIUM: 0, HIGH: 0 });
  });
});
