/**
 * Defence in depth for the family surface.
 *
 * MASTER.md §11 requires the family API client to intercept restricted fields
 * itself rather than trusting Core not to send them, and §10.3 requires that a
 * Draft / Needs-Review report is never rendered. Both are on the AGENTS.md §4
 * zero-tolerance list, so neither may rest on a single upstream check.
 *
 * These run on the RAW Core payload, before it is mapped to a view type —
 * mapping drops unknown keys, which would hide exactly the leak we want to see.
 */

import type { FamilyReportStatus } from './family-reports';

/**
 * Statuses a family member may see at all. Everything else is either not yet a
 * fact (DRAFT, NEEDS_REVIEW) or not a valid one (STALE).
 *
 * WITHDRAWN is included on purpose: §10.3 requires the withdrawal itself to be
 * visible. The card renders no items for it, so no withdrawn content leaks.
 */
const FAMILY_VISIBLE_STATUSES: ReadonlySet<string> = new Set<FamilyReportStatus>([
  'PUBLISHED',
  'WITHDRAWN',
]);

export function isFamilyVisibleStatus(status: string): boolean {
  return FAMILY_VISIBLE_STATUSES.has(status);
}

/**
 * MASTER.md §11's restricted list, normalised so a casing or camelCase change
 * upstream cannot slip past: keys are lowercased with `_` and `-` removed.
 */
const RESTRICTED_KEYS: ReadonlySet<string> = new Set([
  // 逐字稿
  'transcript',
  'transcripttext',
  'rawtranscript',
  'utterance',
  'utterancetext',
  // ASR 信心值
  'asrconfidence',
  'confidence',
  'confidenceband',
  'confidencescore',
  // 內部照護筆記
  'internalnote',
  'internalnotes',
  'carenote',
  'carenotes',
  'caregivernote',
  // 未覆核事件
  'unreviewedevents',
  'eventcandidates',
  'candidateevents',
  // 診斷式分數
  'riskscore',
  'healthscore',
  'emotionscore',
  'lonelinessscore',
  'diagnosis',
  'diagnosticscore',
  // 完整 Prompt
  'prompt',
  'systemprompt',
  'fullprompt',
  'promptversion',
]);

/** Bounds the walk so a cyclic or absurdly nested payload cannot hang the page. */
const MAX_DEPTH = 12;

function normaliseKey(key: string): string {
  return key.toLowerCase().replace(/[_-]/g, '');
}

export class FamilyDataRedlineError extends Error {
  constructor(public readonly field: string) {
    // The key NAME only. Never the value — AGENTS.md §8.1 forbids echoing a
    // rejected value back, and the value here is the restricted data itself.
    super(`Core returned a field the family surface must never receive: ${field}`);
    this.name = 'FamilyDataRedlineError';
  }
}

/**
 * Throws on the first restricted key found anywhere in `payload`.
 *
 * Hard failure is deliberate here, unlike the status filter below: a response
 * carrying a transcript means the contract is broken in a way we cannot bound,
 * so rendering the rest of it would be guessing about what else is wrong.
 */
export function assertNoRestrictedFields(payload: unknown, depth = 0): void {
  if (depth > MAX_DEPTH || payload === null || typeof payload !== 'object') return;

  if (Array.isArray(payload)) {
    for (const entry of payload) assertNoRestrictedFields(entry, depth + 1);
    return;
  }

  for (const [key, value] of Object.entries(payload)) {
    if (RESTRICTED_KEYS.has(normaliseKey(key))) {
      throw new FamilyDataRedlineError(key);
    }
    assertNoRestrictedFields(value, depth + 1);
  }
}

/**
 * Drops reports the family may not see, and reports the contract violation.
 *
 * Dropping rather than throwing is the right trade here: an unpublished report
 * that never reaches the DOM has leaked nothing, and failing the whole page
 * would deny a legitimate family member the reports they are entitled to
 * because of one bad row. The violation is still surfaced, because silently
 * swallowing it would hide a Core bug behind a page that looks fine.
 *
 * Nothing is shown to the family about the dropped rows — learning that a draft
 * exists is itself disclosure (§10.3).
 */
export function keepFamilyVisible<T extends { status: string; report_id?: string }>(
  reports: readonly T[],
): T[] {
  const visible: T[] = [];
  for (const report of reports) {
    if (isFamilyVisibleStatus(report.status)) {
      visible.push(report);
      continue;
    }
    // Status and id only: neither is restricted content, and the id is what
    // makes the Core-side bug findable.
    console.error(
      '[family] Core returned a report the family surface must not render; dropped it.',
      { status: report.status, reportId: report.report_id ?? '(unknown)' },
    );
  }
  return visible;
}
