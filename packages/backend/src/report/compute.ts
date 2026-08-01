import type { ConversationRecord, EventRecord, EventType, ReportResponse } from '@elderly-care/shared';
import { DynamoTable, Keys } from '../db/index.js';

const EVENT_TYPES: EventType[] = ['meal', 'activity', 'sleep', 'medication_statement', 'emotion', 'important_event'];

function rangeStart(range: 'week' | 'year', now: Date): Date {
  const start = new Date(now);
  if (range === 'week') start.setDate(start.getDate() - 7);
  else start.setFullYear(start.getFullYear() - 1);
  return start;
}

/**
 * A07.1-A07.4 — shared by the caregiver-facing REST handler (api/reports.ts)
 * and the elder-facing voice shortcut (workflow/stage-handlers/llm-handler.ts,
 * triggered by report/intent.ts). Only counts events that passed schema
 * validation and are already persisted — no code path here fabricates or
 * infers a data point beyond what's in DynamoDB (A07.4).
 */
export async function computeReport(table: DynamoTable, elderId: string, range: 'week' | 'year'): Promise<ReportResponse> {
  const now = new Date();
  const dateFrom = rangeStart(range, now).toISOString().slice(0, 10);
  const dateTo = now.toISOString().slice(0, 10);

  const [events, conversations] = await Promise.all([
    table.queryByPk<EventRecord>(Keys.elderPk(elderId), Keys.eventSkPrefix()),
    table.queryByPk<ConversationRecord>(Keys.elderPk(elderId), Keys.conversationSkPrefix()),
  ]);

  const inRange = events.filter((e) => e.eventDate >= dateFrom && e.eventDate <= dateTo);
  const eventCountByType = Object.fromEntries(
    EVENT_TYPES.map((t) => [t, inRange.filter((e) => e.eventType === t).length]),
  ) as Record<EventType, number>;

  const totalInteractions = conversations.filter((c) => c.startTime.slice(0, 10) >= dateFrom).length;

  const rangeLabel = range === 'week' ? '這一週' : '這一年';
  const voiceSummary = `${rangeLabel}您總共互動了 ${totalInteractions} 次，飲食紀錄 ${eventCountByType.meal} 筆，活動紀錄 ${eventCountByType.activity} 筆，睡眠紀錄 ${eventCountByType.sleep} 筆。`;

  return { range, dateFrom, dateTo, eventCountByType, totalInteractions, voiceSummary };
}
