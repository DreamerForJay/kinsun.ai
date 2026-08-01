'use client';

import { useState } from 'react';
import { careEventState, StateBadge } from '@/components/StateCard';
import type { CareEventDecision, EventView } from '@/lib/api/events';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';

const DECISIONS: CareEventDecision[] = ['VERIFY', 'CORRECT', 'REJECT', 'EXCLUDE'];

export interface EventTableProps {
  events: EventView[];
  onReview: (
    event: EventView,
    decision: CareEventDecision,
    correctedContent?: string,
  ) => Promise<void>;
}

export function EventTable({ events, onReview }: EventTableProps) {
  const { t } = useLocale();
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
    return <p style={{ color: '#718096' }}>{t('eventTable.empty')}</p>;
  }

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 15 }}>
      <thead>
        <tr style={{ textAlign: 'left', borderBottom: '2px solid #e2e8f0' }}>
          <th style={{ padding: 8 }}>{t('eventTable.colDate')}</th>
          <th style={{ padding: 8 }}>{t('eventTable.colType')}</th>
          <th style={{ padding: 8 }}>{t('eventTable.colContent')}</th>
          <th style={{ padding: 8 }}>{t('eventTable.colConfidence')}</th>
          <th style={{ padding: 8 }}>{t('eventTable.colStatus')}</th>
          <th style={{ padding: 8 }}>{t('eventTable.colEvidence')}</th>
          <th style={{ padding: 8 }}>{t('eventTable.colActions')}</th>
        </tr>
      </thead>
      <tbody>
        {events.map((event) => (
          <tr key={event.eventId} style={{ borderBottom: '1px solid #edf2f7' }}>
            <td style={{ padding: 8 }}>{event.eventDate}</td>
            <td style={{ padding: 8 }}>{t(`eventType.${event.eventType}` as MessageKey)}</td>
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
            <td style={{ padding: 8 }}>{t(`confidence.${event.confidenceBand}` as MessageKey)}</td>
            {/* A table cell has no room for the full card, so the status column
                carries the colour+icon+text half of §4.2. The dashed-outline
                shape lives on the card components. */}
            <td style={{ padding: 8 }}>
              <StateBadge
                state={careEventState(event.status)}
                label={t(`eventStatus.${event.status}` as MessageKey)}
              />
            </td>
            <td style={{ padding: 8, fontSize: 12, color: '#718096' }}>
              {t('eventTable.evidenceVersion', {
                evidence: event.evidenceRefs.length,
                version: event.version,
              })}
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
                    {/* option value stays the Core enum; only the label is translated */}
                    {DECISIONS.map((item) => (
                      <option key={item} value={item}>
                        {t(`decision.${item}` as MessageKey)}
                      </option>
                    ))}
                  </select>
                  <button type="button" disabled={saving} onClick={() => save(event)}>
                    {t('eventTable.submit')}
                  </button>
                  <button type="button" disabled={saving} onClick={() => setEditingId(null)}>
                    {t('eventTable.cancel')}
                  </button>
                </div>
              ) : (
                <button type="button" onClick={() => startReview(event)}>
                  {t('eventTable.review')}
                </button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
