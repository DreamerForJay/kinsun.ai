import { describe, expect, it } from 'vitest';
import { careEventState, familyReportState, summaryState } from './StateCard';

/* MASTER.md §4.2 standardises the *shape*, so what matters here is that no
   domain value can be drawn as more settled than it is. Every default branch
   therefore has to land on a dashed shape, never on `confirmed`/`published`. */

const DASHED = ['candidate', 'dataInsufficient'];

describe('careEventState', () => {
  it('maps each care-event status to its §4.2 shape', () => {
    expect(careEventState('CANDIDATE')).toBe('candidate');
    expect(careEventState('NEEDS_REVIEW')).toBe('needsReview');
    expect(careEventState('VERIFIED')).toBe('confirmed');
    expect(careEventState('CORRECTED')).toBe('confirmed');
    expect(careEventState('REJECTED')).toBe('withdrawn');
    expect(careEventState('EXCLUDED')).toBe('withdrawn');
  });

  it('never renders an unknown status as settled', () => {
    expect(DASHED).toContain(careEventState('SOMETHING_NEW'));
    expect(DASHED).toContain(careEventState(''));
  });
});

describe('summaryState', () => {
  it('maps each summary status to its §4.2 shape', () => {
    expect(summaryState('DRAFT')).toBe('candidate');
    expect(summaryState('READY')).toBe('needsReview');
    expect(summaryState('NEEDS_REVIEW')).toBe('needsReview');
    expect(summaryState('PUBLISHED')).toBe('published');
    expect(summaryState('WITHDRAWN')).toBe('withdrawn');
    expect(summaryState('STALE')).toBe('dataInsufficient');
  });

  it('never renders an unknown status as settled', () => {
    expect(DASHED).toContain(summaryState('SOMETHING_NEW'));
  });
});

describe('familyReportState', () => {
  it('maps the two statuses the family may see', () => {
    expect(familyReportState('PUBLISHED')).toBe('published');
    expect(familyReportState('WITHDRAWN')).toBe('withdrawn');
  });

  /* family-guard filters these out first. If one ever slips through, the card
     must not present it as a published fact — that is the §10.3 red line. */
  it('never draws an unpublished report as published', () => {
    expect(familyReportState('DRAFT')).not.toBe('published');
    expect(familyReportState('NEEDS_REVIEW')).not.toBe('published');
    expect(familyReportState('STALE')).not.toBe('published');
    expect(DASHED).toContain(familyReportState('DRAFT'));
  });
});
