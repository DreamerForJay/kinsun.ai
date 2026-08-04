import { apiFetch, createIdempotencyKey, type ApiConfig } from './client';

export type CoreCareEventType =
  | 'MEAL'
  | 'ACTIVITY'
  | 'SLEEP'
  | 'MEDICATION_STATEMENT'
  | 'EMOTION_EXPRESSION'
  | 'SOCIAL_CONTACT'
  | 'EXPECTED_CONTACT_MISSED'
  | 'ACTIVITY_PARTICIPATION'
  | 'ACTIVITY_CANCELLED'
  | 'COMPANIONSHIP_NEED';

export type CoreCareEventStatus =
  'CANDIDATE' | 'NEEDS_REVIEW' | 'VERIFIED' | 'CORRECTED' | 'REJECTED' | 'EXCLUDED';

export type CareEventDecision = 'VERIFY' | 'CORRECT' | 'REJECT' | 'EXCLUDE';
export type ConfidenceBand = 'LOW' | 'MEDIUM' | 'HIGH';

interface CoreCareEvent {
  event_id: string;
  elder_id: string;
  event_type: CoreCareEventType;
  event_time: string | null;
  status: CoreCareEventStatus | 'DELETED';
  structured_payload: Record<string, unknown>;
  evidence_refs: string[];
  confidence_band: ConfidenceBand;
  version: number;
  consent_version: number;
  created_at: string;
  updated_at: string;
}

interface CoreCareEventList {
  items: CoreCareEvent[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface EventView {
  eventId: string;
  elderId: string;
  eventType: CoreCareEventType;
  eventDate: string;
  content: string;
  status: CoreCareEventStatus;
  confidenceBand: ConfidenceBand;
  evidenceRefs: string[];
  version: number;
  consentVersion: number;
  structuredPayload: Record<string, unknown>;
}

export interface ListEventsFilters {
  dateFrom?: string;
  dateTo?: string;
  eventType?: CoreCareEventType;
  status?: CoreCareEventStatus;
  cursor?: string;
}

export interface ListEventsResult {
  items: EventView[];
  nextCursor: string | null;
}

function displayContent(payload: Record<string, unknown>): string {
  for (const key of ['summary', 'content', 'description', 'text']) {
    const value = payload[key];
    if (typeof value === 'string' && value.trim()) return value;
  }
  return Object.keys(payload).length > 0 ? JSON.stringify(payload) : '未提供結構化內容';
}

function toEventView(event: CoreCareEvent): EventView {
  if (event.status === 'DELETED') {
    throw new Error('CORE_RETURNED_DELETED_CARE_EVENT');
  }
  return {
    eventId: event.event_id,
    elderId: event.elder_id,
    eventType: event.event_type,
    eventDate: (event.event_time ?? event.created_at).slice(0, 10),
    content: displayContent(event.structured_payload),
    status: event.status,
    confidenceBand: event.confidence_band,
    evidenceRefs: event.evidence_refs,
    version: event.version,
    consentVersion: event.consent_version,
    structuredPayload: event.structured_payload,
  };
}

/** Core applies every filter before opaque-cursor pagination. */
export async function listEvents(
  config: ApiConfig,
  elderId: string,
  filters: ListEventsFilters = {},
): Promise<ListEventsResult> {
  const params = new URLSearchParams();
  if (filters.status) params.append('status', filters.status);
  if (filters.eventType) params.set('event_type', filters.eventType);
  if (filters.dateFrom) params.set('date_from', filters.dateFrom);
  if (filters.dateTo) params.set('date_to', filters.dateTo);
  if (filters.cursor) params.set('cursor', filters.cursor);
  params.set('limit', '100');

  const result = await apiFetch<CoreCareEventList>(
    config,
    `/api/v1/elders/${elderId}/care-events?${params.toString()}`,
  );
  return {
    items: result.items.map(toEventView),
    nextCursor: result.next_cursor,
  };
}

export interface NeedsReviewSummary {
  count: number;
  /**
   * True when Core returned a further page, so `count` is a floor rather than a
   * total. Pagination is opaque-cursor only and deliberately exposes no `total`
   * (AGENTS.md §8.1), so an exact figure is not available — and displaying one
   * anyway would state an unknown as a fact (§4).
   */
  atLeast: boolean;
  /** Why they need review, from the band Core already assigns. */
  byConfidence: Record<ConfidenceBand, number>;
}

/**
 * Counts the care events waiting on this caregiver, for MASTER.md §10.2's
 * Needs Review state ("顯示數量與原因").
 *
 * Requests only the review status: date and type filters are valid server-side
 * view filters, but applying them here would undercount the whole review queue.
 */
export async function summariseNeedsReview(
  config: ApiConfig,
  elderId: string,
): Promise<NeedsReviewSummary> {
  const result = await listEvents(config, elderId, { status: 'NEEDS_REVIEW' });
  const byConfidence: Record<ConfidenceBand, number> = { LOW: 0, MEDIUM: 0, HIGH: 0 };
  for (const event of result.items) byConfidence[event.confidenceBand] += 1;

  return {
    count: result.items.length,
    atLeast: result.nextCursor !== null,
    byConfidence,
  };
}

function correctedPayload(event: EventView, content: string): Record<string, unknown> {
  const payload = { ...event.structuredPayload };
  const existingKey = ['summary', 'content', 'description', 'text'].find(
    (key) => typeof payload[key] === 'string',
  );
  payload[existingKey ?? 'content'] = content;
  return payload;
}

export async function reviewEvent(
  config: ApiConfig,
  elderId: string,
  event: EventView,
  decision: CareEventDecision,
  correctedContent?: string,
): Promise<EventView> {
  const result = await apiFetch<CoreCareEvent>(
    config,
    `/api/v1/elders/${elderId}/care-events/${event.eventId}/review`,
    {
      method: 'POST',
      headers: { 'Idempotency-Key': createIdempotencyKey('care-event-review') },
      body: JSON.stringify({
        decision,
        reason_code: 'CAREGIVER_UI_REVIEW',
        corrected_payload:
          decision === 'CORRECT'
            ? correctedPayload(event, correctedContent ?? event.content)
            : null,
        expected_version: event.version,
      }),
    },
  );
  return toEventView(result);
}
