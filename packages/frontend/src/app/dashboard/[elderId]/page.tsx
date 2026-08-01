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
import { getRuntimeConfig, type RuntimeConfig } from '@/lib/runtime-config';

type Tab = 'events' | 'memories' | 'summaries';

const SUMMARY_STATUS_LABEL: Record<SummaryView['status'], string> = {
  DRAFT: '草稿',
  READY: '可供覆核',
  NEEDS_REVIEW: '待覆核',
  PUBLISHED: '已發布',
  STALE: '需重建',
  WITHDRAWN: '已撤回',
};

function describeError(error: unknown, fallback: string): string {
  if (error instanceof ApiRequestError && (error.status === 403 || error.status === 404)) {
    return '目前身分沒有查看或操作這位長者資料的權限。';
  }
  if (error instanceof ApiRequestError && error.status === 409) {
    return '資料版本已更新，請重新載入後再操作。';
  }
  return fallback;
}

export default function ElderDetailPage({ params }: { params: { elderId: string } }) {
  const { elderId } = params;
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
  const [error, setError] = useState<string | null>(null);

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
    setError(null);
    listEvents(apiConfig, elderId, eventFilters)
      .then((response) => setEvents(response.items))
      .catch((caught) => setError(describeError(caught, '讀取事件失敗')));
  }, [apiConfig, elderId, eventFilters]);

  const loadMemories = useCallback(() => {
    setError(null);
    listMemories(apiConfig, elderId)
      .then(setMemories)
      .catch((caught) => setError(describeError(caught, '讀取記憶失敗')));
  }, [apiConfig, elderId]);

  const loadSummaries = useCallback(() => {
    setError(null);
    listSummaries(apiConfig, elderId)
      .then((response) => setSummaries(response.items))
      .catch((caught) => setError(describeError(caught, '讀取摘要失敗')));
  }, [apiConfig, elderId]);

  useEffect(() => {
    if (runtimeConfig?.credentialStatus !== 'present') return;
    if (tab === 'events') loadEvents();
    if (tab === 'memories') loadMemories();
    if (tab === 'summaries') loadSummaries();
  }, [tab, runtimeConfig?.credentialStatus, loadEvents, loadMemories, loadSummaries]);

  if (!runtimeConfig) return null;
  if (runtimeConfig.credentialStatus === 'unavailable') {
    return <NotLoggedIn reason="無法確認登入憑證狀態；系統已停止，不會略過認證" />;
  }
  if (runtimeConfig.credentialStatus !== 'present') {
    return <NotLoggedIn reason="尚未設定登入資訊，請先完成登入設定" />;
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
      setError(describeError(caught, '覆核事件失敗'));
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

  return (
    <main style={{ maxWidth: 960, margin: '0 auto', padding: 24 }}>
      <h1 style={{ fontSize: 22, marginBottom: 4 }}>長者詳情</h1>
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
            style={{
              padding: '8px 16px',
              border: 'none',
              borderBottom: tab === item ? '2px solid #2b6cb0' : '2px solid transparent',
              background: 'none',
              fontWeight: tab === item ? 700 : 400,
              cursor: 'pointer',
            }}
          >
            {item === 'events' ? '照護事件' : item === 'memories' ? '記憶管理' : '每日摘要'}
          </button>
        ))}
      </div>

      {error && <p style={{ color: '#e53e3e' }}>{error}</p>}

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
          <p style={{ color: '#718096' }}>
            Core API 目前僅提供摘要讀取；摘要發布與家屬報表是不同的正式流程。
          </p>
          {summaries.length === 0 && <p style={{ color: '#718096' }}>目前沒有正式摘要。</p>}
          {summaries.map((summary) => (
            <section
              key={summary.summaryId}
              style={{ padding: 12, border: '1px solid #e2e8f0', borderRadius: 8 }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <strong>{summary.date}</strong>
                <span>{SUMMARY_STATUS_LABEL[summary.status]}</span>
                <span style={{ fontSize: 12, color: '#718096' }}>版本 {summary.version}</span>
              </div>
              {summary.items.length === 0 ? (
                <p style={{ color: '#718096' }}>沒有可顯示的來源支持項目。</p>
              ) : (
                <ul>
                  {summary.items.map((item, index) => (
                    <li key={`${item.category}-${index}`}>
                      [{item.category}] {item.text}（來源 {item.sourceEventIds.length} 筆）
                    </li>
                  ))}
                </ul>
              )}
              {summary.missingFields.length > 0 && (
                <p style={{ color: '#718096' }}>資料缺口：{summary.missingFields.join('、')}</p>
              )}
            </section>
          ))}
        </div>
      )}
    </main>
  );
}
