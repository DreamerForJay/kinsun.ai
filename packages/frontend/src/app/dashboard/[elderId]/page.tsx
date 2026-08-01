'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { EventFilterBar } from '@/components/dashboard/EventFilterBar';
import { EventTable } from '@/components/dashboard/EventTable';
import { MemoryList } from '@/components/dashboard/MemoryList';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { ApiRequestError } from '@/lib/api/client';
import {
  listEvents,
  reviewEvent,
  type CareEventDecision,
  type EventView,
  type ListEventsFilters,
} from '@/lib/api/events';
import {
  confirmMemory,
  deleteMemory,
  listMemories,
  rejectMemory,
  type MemoryListView,
  type MemoryView,
} from '@/lib/api/memories';
import { listSummaries, type SummaryView } from '@/lib/api/summaries';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';
import { getRuntimeConfig, type RuntimeConfig } from '@/lib/runtime-config';

type Tab = 'events' | 'memories' | 'summaries';

const TAB_LABEL: Record<Tab, MessageKey> = {
  events: 'elderDetail.tabEvents',
  memories: 'elderDetail.tabMemories',
  summaries: 'elderDetail.tabSummaries',
};

/** Returns a key rather than a string so a stored error re-renders in the
 *  language selected *now*, not the one active when it was raised. */
function describeError(error: unknown, fallback: MessageKey): MessageKey {
  if (error instanceof ApiRequestError && (error.status === 403 || error.status === 404)) {
    return 'error.noElderDataPermission';
  }
  if (error instanceof ApiRequestError && error.status === 409) {
    return 'error.versionConflict';
  }
  return fallback;
}

export default function ElderDetailPage({ params }: { params: { elderId: string } }) {
  const { elderId } = params;
  const { t, locale } = useLocale();
  const [runtimeConfig, setRuntimeConfig] = useState<RuntimeConfig | null>(null);
  const apiConfig = useMemo(
    () => ({ apiBaseUrl: runtimeConfig?.apiBaseUrl ?? '/backend/core' }),
    [runtimeConfig?.apiBaseUrl],
  );
  const [tab, setTab] = useState<Tab>('events');
  const [events, setEvents] = useState<EventView[]>([]);
  const [eventFilters, setEventFilters] = useState<ListEventsFilters>({});
  const [memories, setMemories] = useState<MemoryListView>({ candidates: [], confirmed: [] });
  const [summaries, setSummaries] = useState<SummaryView[]>([]);
  const [errorKey, setErrorKey] = useState<MessageKey | null>(null);

  useEffect(() => {
    let cancelled = false;
    void getRuntimeConfig().then((nextConfig) => {
      if (!cancelled) setRuntimeConfig(nextConfig);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const loadEvents = useCallback(() => {
    setErrorKey(null);
    listEvents(apiConfig, elderId, eventFilters)
      .then((response) => setEvents(response.items))
      .catch((caught) => setErrorKey(describeError(caught, 'error.loadEventsFailed')));
  }, [apiConfig, elderId, eventFilters]);

  const loadMemories = useCallback(() => {
    setErrorKey(null);
    listMemories(apiConfig, elderId)
      .then(setMemories)
      .catch((caught) => setErrorKey(describeError(caught, 'error.loadMemoriesFailed')));
  }, [apiConfig, elderId]);

  const loadSummaries = useCallback(() => {
    setErrorKey(null);
    listSummaries(apiConfig, elderId)
      .then((response) => setSummaries(response.items))
      .catch((caught) => setErrorKey(describeError(caught, 'error.loadSummariesFailed')));
  }, [apiConfig, elderId]);

  useEffect(() => {
    if (runtimeConfig?.credentialStatus !== 'present') return;
    if (tab === 'events') loadEvents();
    if (tab === 'memories') loadMemories();
    if (tab === 'summaries') loadSummaries();
  }, [tab, runtimeConfig?.credentialStatus, loadEvents, loadMemories, loadSummaries]);

  if (!runtimeConfig) return null;
  if (runtimeConfig.credentialStatus === 'unavailable') {
    return <NotLoggedIn reason={t('auth.credentialUnavailable')} linkLabel={t('common.signIn')} />;
  }
  if (runtimeConfig.credentialStatus !== 'present') {
    return <NotLoggedIn reason={t('auth.credentialMissing')} linkLabel={t('common.signIn')} />;
  }

  async function handleReviewEvent(
    event: EventView,
    decision: CareEventDecision,
    correctedContent?: string,
  ) {
    try {
      await reviewEvent(apiConfig, elderId, event, decision, correctedContent);
      loadEvents();
    } catch (caught) {
      setErrorKey(describeError(caught, 'error.reviewEventFailed'));
      throw caught;
    }
  }

  async function handleConfirmMemory(memory: MemoryView) {
    await confirmMemory(apiConfig, elderId, memory);
    loadMemories();
  }

  async function handleRejectMemory(memory: MemoryView) {
    await rejectMemory(apiConfig, elderId, memory);
    loadMemories();
  }

  async function handleDeleteMemory(memory: MemoryView) {
    await deleteMemory(apiConfig, elderId, memory);
    loadMemories();
  }

  const listSeparator = locale === 'en' ? ', ' : '、';

  return (
    <main style={{ maxWidth: 960, margin: '0 auto', padding: 24 }}>
      <h1 style={{ fontSize: 22, marginBottom: 4 }}>{t('elderDetail.title')}</h1>
      <p style={{ color: '#718096', marginBottom: 20 }}>Elder ID: {elderId}</p>

      <div
        style={{
          display: 'flex',
          gap: 12,
          marginBottom: 20,
          borderBottom: '1px solid #e2e8f0',
        }}
      >
        {(['events', 'memories', 'summaries'] as Tab[]).map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => setTab(item)}
            aria-pressed={tab === item}
            style={{
              padding: '8px 16px',
              border: 'none',
              borderBottom: tab === item ? '2px solid #2b6cb0' : '2px solid transparent',
              background: 'none',
              fontWeight: tab === item ? 700 : 400,
              cursor: 'pointer',
            }}
          >
            {t(TAB_LABEL[item])}
          </button>
        ))}
      </div>

      {errorKey && <p style={{ color: '#e53e3e' }}>{t(errorKey)}</p>}

      {tab === 'events' && (
        <>
          <EventFilterBar filters={eventFilters} onChange={setEventFilters} />
          <EventTable events={events} onReview={handleReviewEvent} />
        </>
      )}

      {tab === 'memories' && (
        <MemoryList
          candidates={memories.candidates}
          confirmed={memories.confirmed}
          onConfirm={handleConfirmMemory}
          onReject={handleRejectMemory}
          onDelete={handleDeleteMemory}
        />
      )}

      {tab === 'summaries' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <p style={{ color: '#718096' }}>{t('elderDetail.summaryNotice')}</p>
          {summaries.length === 0 && (
            <p style={{ color: '#718096' }}>{t('elderDetail.summaryEmpty')}</p>
          )}
          {summaries.map((summary) => (
            <section
              key={summary.summaryId}
              style={{ padding: 12, border: '1px solid #e2e8f0', borderRadius: 8 }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <strong>{summary.date}</strong>
                <span>{t(`summaryStatus.${summary.status}` as MessageKey)}</span>
                <span style={{ fontSize: 12, color: '#718096' }}>
                  {t('common.version', { version: summary.version })}
                </span>
              </div>
              {summary.items.length === 0 ? (
                <p style={{ color: '#718096' }}>{t('elderDetail.summaryNoItems')}</p>
              ) : (
                <ul>
                  {summary.items.map((item, index) => (
                    <li key={`${item.category}-${index}`}>
                      [{item.category}] {item.text}
                      {t('common.sources', { count: item.sourceEventIds.length })}
                    </li>
                  ))}
                </ul>
              )}
              {summary.missingFields.length > 0 && (
                <p style={{ color: '#718096' }}>
                  {t('elderDetail.dataGaps', {
                    fields: summary.missingFields.join(listSeparator),
                  })}
                </p>
              )}
            </section>
          ))}
        </div>
      )}
    </main>
  );
}
