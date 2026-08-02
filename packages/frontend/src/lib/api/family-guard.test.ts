import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ApiConfig } from './client';
import {
  assertNoRestrictedFields,
  FamilyDataRedlineError,
  isFamilyVisibleStatus,
  keepFamilyVisible,
} from './family-guard';
import { listFamilyReports } from './family-reports';

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

function report(overrides: Record<string, unknown> = {}) {
  return {
    report_id: 'report-1',
    elder_id: 'elder-1',
    recipient_scope_ids: ['scope-1'],
    report_type: 'DAILY',
    period_start: '2026-08-01',
    period_end: '2026-08-01',
    status: 'PUBLISHED',
    items: [{ category: 'MEAL', text: '午餐吃了魚', source_ids: ['event-1'] }],
    data_gap_notice: null,
    sensitive_review_required: false,
    version: 1,
    published_at: '2026-08-01T09:00:00Z',
    withdrawn_at: null,
    updated_at: '2026-08-01T09:00:00Z',
    ...overrides,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('assertNoRestrictedFields', () => {
  it('accepts a well-formed family report payload', () => {
    expect(() => assertNoRestrictedFields({ items: [report()] })).not.toThrow();
  });

  it('rejects a transcript at the top level', () => {
    expect(() => assertNoRestrictedFields({ transcript: '長者說的原話' })).toThrow(
      FamilyDataRedlineError,
    );
  });

  it('rejects restricted fields nested inside items', () => {
    const payload = { items: [report({ items: [{ category: 'MEAL', asr_confidence: 0.42 }] })] };
    expect(() => assertNoRestrictedFields(payload)).toThrow(FamilyDataRedlineError);
  });

  /* Core is contracted to send snake_case, but the guard must not become a
     no-op if some layer between here and Core ever re-cases the payload. */
  it('catches casing and camelCase variants', () => {
    expect(() => assertNoRestrictedFields({ asrConfidence: 0.4 })).toThrow(FamilyDataRedlineError);
    expect(() => assertNoRestrictedFields({ Internal_Note: 'x' })).toThrow(FamilyDataRedlineError);
    expect(() => assertNoRestrictedFields({ RISK_SCORE: 3 })).toThrow(FamilyDataRedlineError);
  });

  /* AGENTS.md §8.1 forbids echoing a rejected value; here the value IS the
     restricted data, so only the key name may appear. */
  it('names the offending field without quoting its value', () => {
    const secret = '長者的完整逐字稿內容';
    try {
      assertNoRestrictedFields({ transcript: secret });
      expect.unreachable('should have thrown');
    } catch (error) {
      expect(error).toBeInstanceOf(FamilyDataRedlineError);
      expect((error as Error).message).toContain('transcript');
      expect((error as Error).message).not.toContain(secret);
    }
  });

  it('does not flag legitimate family report fields', () => {
    expect(() =>
      assertNoRestrictedFields({
        data_gap_notice: '今日資料不足',
        sensitive_review_required: false,
        source_ids: ['a'],
        version: 2,
      }),
    ).not.toThrow();
  });

  it('tolerates primitives, null and deep nesting without throwing', () => {
    let deep: unknown = { leaf: true };
    for (let i = 0; i < 40; i += 1) deep = { nested: deep };
    expect(() => assertNoRestrictedFields(deep)).not.toThrow();
    expect(() => assertNoRestrictedFields(null)).not.toThrow();
    expect(() => assertNoRestrictedFields('string')).not.toThrow();
  });
});

describe('keepFamilyVisible', () => {
  it('classifies only PUBLISHED and WITHDRAWN as family-visible', () => {
    expect(isFamilyVisibleStatus('PUBLISHED')).toBe(true);
    expect(isFamilyVisibleStatus('WITHDRAWN')).toBe(true);
    expect(isFamilyVisibleStatus('DRAFT')).toBe(false);
    expect(isFamilyVisibleStatus('NEEDS_REVIEW')).toBe(false);
    expect(isFamilyVisibleStatus('STALE')).toBe(false);
  });

  it('drops unpublished reports and reports the violation', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    const kept = keepFamilyVisible([
      { status: 'PUBLISHED', report_id: 'a' },
      { status: 'DRAFT', report_id: 'b' },
      { status: 'NEEDS_REVIEW', report_id: 'c' },
      { status: 'WITHDRAWN', report_id: 'd' },
      { status: 'STALE', report_id: 'e' },
    ]);

    expect(kept.map((entry) => entry.report_id)).toEqual(['a', 'd']);
    expect(consoleError).toHaveBeenCalledTimes(3);
  });

  it('stays quiet when every report is visible', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    keepFamilyVisible([{ status: 'PUBLISHED', report_id: 'a' }]);
    expect(consoleError).not.toHaveBeenCalled();
  });
});

describe('listFamilyReports', () => {
  it('never returns a Draft or Needs-Review report to the caller', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        success({
          items: [
            report({ report_id: 'published-1', status: 'PUBLISHED' }),
            report({ report_id: 'draft-1', status: 'DRAFT' }),
            report({ report_id: 'review-1', status: 'NEEDS_REVIEW' }),
          ],
        }),
      ),
    );

    const reports = await listFamilyReports(config, 'elder-1');

    expect(reports.map((entry) => entry.reportId)).toEqual(['published-1']);
  });

  /* The guard runs before toFamilyReportView, which keeps only known keys —
     without that ordering a leaked transcript would be dropped silently and
     the broken contract would never surface. */
  it('fails loudly when Core leaks a restricted field', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => success({ items: [report({ transcript: '長者說的原話' })] })),
    );

    await expect(listFamilyReports(config, 'elder-1')).rejects.toBeInstanceOf(
      FamilyDataRedlineError,
    );
  });

  it('passes a clean response through unchanged', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => success({ items: [report()] })),
    );

    const reports = await listFamilyReports(config, 'elder-1');

    expect(reports).toHaveLength(1);
    expect(reports[0]?.items[0]?.text).toBe('午餐吃了魚');
  });
});
