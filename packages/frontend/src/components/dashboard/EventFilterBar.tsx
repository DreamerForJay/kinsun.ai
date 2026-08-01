'use client';

import type { CoreCareEventStatus, CoreCareEventType, ListEventsFilters } from '@/lib/api/events';

export interface EventFilterBarProps {
  filters: ListEventsFilters;
  onChange: (filters: ListEventsFilters) => void;
}

const EVENT_TYPES: CoreCareEventType[] = [
  'MEAL',
  'ACTIVITY',
  'SLEEP',
  'MEDICATION_STATEMENT',
  'EMOTION_EXPRESSION',
  'SOCIAL_CONTACT',
  'EXPECTED_CONTACT_MISSED',
  'ACTIVITY_PARTICIPATION',
  'ACTIVITY_CANCELLED',
  'COMPANIONSHIP_NEED',
];
const EVENT_STATUSES: CoreCareEventStatus[] = [
  'CANDIDATE',
  'NEEDS_REVIEW',
  'VERIFIED',
  'CORRECTED',
  'REJECTED',
  'EXCLUDED',
];

export function EventFilterBar({ filters, onChange }: EventFilterBarProps) {
  return (
    <div
      style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}
    >
      <label>
        起始日期{' '}
        <input
          type="date"
          value={filters.dateFrom ?? ''}
          onChange={(event) => onChange({ ...filters, dateFrom: event.target.value || undefined })}
        />
      </label>
      <label>
        結束日期{' '}
        <input
          type="date"
          value={filters.dateTo ?? ''}
          onChange={(event) => onChange({ ...filters, dateTo: event.target.value || undefined })}
        />
      </label>
      <label>
        類型{' '}
        <select
          value={filters.eventType ?? ''}
          onChange={(event) =>
            onChange({
              ...filters,
              eventType: (event.target.value || undefined) as CoreCareEventType | undefined,
            })
          }
        >
          <option value="">全部</option>
          {EVENT_TYPES.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
      </label>
      <label>
        狀態{' '}
        <select
          value={filters.status ?? ''}
          onChange={(event) =>
            onChange({
              ...filters,
              status: (event.target.value || undefined) as CoreCareEventStatus | undefined,
            })
          }
        >
          <option value="">正式事件</option>
          {EVENT_STATUSES.map((status) => (
            <option key={status} value={status}>
              {status}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
