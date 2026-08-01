'use client';

import { useState } from 'react';
import type { CareEventDecision, EventView } from '@/lib/api/events';

const EVENT_TYPE_LABEL: Record<EventView['eventType'], string> = {
  MEAL: '飲食',
  ACTIVITY: '活動',
  SLEEP: '睡眠',
  MEDICATION_STATEMENT: '用藥陳述',
  EMOTION_EXPRESSION: '情緒表達',
  SOCIAL_CONTACT: '社交聯繫',
  EXPECTED_CONTACT_MISSED: '未如期聯繫',
  ACTIVITY_PARTICIPATION: '活動參與',
  ACTIVITY_CANCELLED: '活動取消',
  COMPANIONSHIP_NEED: '陪伴需求',
};

const STATUS_LABEL: Record<EventView['status'], string> = {
  CANDIDATE: '候選',
  NEEDS_REVIEW: '待覆核',
  VERIFIED: '已驗證',
  CORRECTED: '已修正',
  REJECTED: '已拒絕',
  EXCLUDED: '已排除',
};

const CONFIDENCE_LABEL: Record<EventView['confidenceBand'], string> = {
  LOW: '低',
  MEDIUM: '中',
  HIGH: '高',
};

export interface EventTableProps {
  events: EventView[];
  onReview: (
    event: EventView,
    decision: CareEventDecision,
    correctedContent?: string,
  ) => Promise<void>;
}

export function EventTable({ events, onReview }: EventTableProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftContent, setDraftContent] = useState('');
  const [decision, setDecision] = useState<CareEventDecision>('VERIFY');
  const [saving, setSaving] = useState(false);

  function startReview(event: EventView) {
    setEditingId(event.eventId);
    setDraftContent(event.content);
    setDecision('VERIFY');
  }

  async function save(event: EventView) {
    setSaving(true);
    try {
      await onReview(event, decision, decision === 'CORRECT' ? draftContent : undefined);
      setEditingId(null);
    } finally {
      setSaving(false);
    }
  }

  if (events.length === 0) {
    return <p style={{ color: '#718096' }}>沒有符合條件的事件紀錄。</p>;
  }

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 15 }}>
      <thead>
        <tr style={{ textAlign: 'left', borderBottom: '2px solid #e2e8f0' }}>
          <th style={{ padding: 8 }}>日期</th>
          <th style={{ padding: 8 }}>類型</th>
          <th style={{ padding: 8 }}>內容</th>
          <th style={{ padding: 8 }}>信心區間</th>
          <th style={{ padding: 8 }}>狀態</th>
          <th style={{ padding: 8 }}>證據／版本</th>
          <th style={{ padding: 8 }}>操作</th>
        </tr>
      </thead>
      <tbody>
        {events.map((event) => (
          <tr key={event.eventId} style={{ borderBottom: '1px solid #edf2f7' }}>
            <td style={{ padding: 8 }}>{event.eventDate}</td>
            <td style={{ padding: 8 }}>{EVENT_TYPE_LABEL[event.eventType]}</td>
            <td style={{ padding: 8, maxWidth: 280 }}>
              {editingId === event.eventId && decision === 'CORRECT' ? (
                <textarea
                  value={draftContent}
                  onChange={(changeEvent) => setDraftContent(changeEvent.target.value)}
                  style={{ width: '100%' }}
                />
              ) : (
                event.content
              )}
            </td>
            <td style={{ padding: 8 }}>{CONFIDENCE_LABEL[event.confidenceBand]}</td>
            <td style={{ padding: 8 }}>{STATUS_LABEL[event.status]}</td>
            <td style={{ padding: 8, fontSize: 12, color: '#718096' }}>
              證據 {event.evidenceRefs.length} 筆｜版本 {event.version}
            </td>
            <td style={{ padding: 8 }}>
              {editingId === event.eventId ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <select
                    value={decision}
                    onChange={(changeEvent) =>
                      setDecision(changeEvent.target.value as CareEventDecision)
                    }
                  >
                    <option value="VERIFY">驗證</option>
                    <option value="CORRECT">修正</option>
                    <option value="REJECT">拒絕</option>
                    <option value="EXCLUDE">排除</option>
                  </select>
                  <button type="button" disabled={saving} onClick={() => save(event)}>
                    送出覆核
                  </button>
                  <button type="button" disabled={saving} onClick={() => setEditingId(null)}>
                    取消
                  </button>
                </div>
              ) : (
                <button type="button" onClick={() => startReview(event)}>
                  覆核
                </button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
