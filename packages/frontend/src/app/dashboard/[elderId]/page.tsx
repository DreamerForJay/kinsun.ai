'use client';

import { useCallback, useEffect, useState } from 'react';
import type { EventSummary, ListMemoriesResponse, PersonaContext, ReviewStatus, SummaryRecord } from '@elderly-care/shared';
import { EventFilterBar } from '@/components/dashboard/EventFilterBar';
import { EventTable } from '@/components/dashboard/EventTable';
import { MemoryList } from '@/components/dashboard/MemoryList';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { PersonaForm } from '@/components/dashboard/PersonaForm';
import { ApiRequestError } from '@/lib/api/client';
import { listEvents, updateEvent, type ListEventsFilters } from '@/lib/api/events';
import { confirmMemory, deleteMemory, listMemories, rejectMemory } from '@/lib/api/memories';
import { getPersona, updatePersona } from '@/lib/api/persona';
import { listSummaries, publishSummary, withdrawSummary } from '@/lib/api/summaries';
import { getRuntimeConfig } from '@/lib/runtime-config';

type Tab = 'events' | 'memories' | 'summaries' | 'persona';

/** 403 always means the same thing here — caregiver JWT valid, but this elder isn't in their authorizedElderIds. */
function describeError(err: unknown, fallback: string): string {
  if (err instanceof ApiRequestError && err.status === 403) {
    return '您目前沒有查看這位長者資料的權限，請聯絡系統管理員確認授權。';
  }
  return fallback;
}

export default function ElderDetailPage({ params }: { params: { elderId: string } }) {
  const { elderId } = params;
  const [tab, setTab] = useState<Tab>('events');
  const [events, setEvents] = useState<EventSummary[]>([]);
  const [eventFilters, setEventFilters] = useState<ListEventsFilters>({});
  const [memories, setMemories] = useState<ListMemoriesResponse>({ candidates: [], confirmed: [] });
  const [summaries, setSummaries] = useState<SummaryRecord[]>([]);
  const [persona, setPersona] = useState<PersonaContext | null>(null);
  const [error, setError] = useState<string | null>(null);

  const config = getRuntimeConfig();
  const apiConfig = { apiBaseUrl: config.apiBaseUrl, token: config.token };
  const caregiverId = config.caregiverId;

  const loadEvents = useCallback(() => {
    listEvents(apiConfig, elderId, eventFilters)
      .then((res) => setEvents(res.items))
      .catch((err) => setError(describeError(err, '讀取事件失敗')));
  }, [elderId, eventFilters]);

  const loadMemories = useCallback(() => {
    listMemories(apiConfig, elderId)
      .then(setMemories)
      .catch((err) => setError(describeError(err, '讀取記憶失敗')));
  }, [elderId]);

  const loadSummaries = useCallback(() => {
    listSummaries(apiConfig, elderId)
      .then((res) => setSummaries(res.items))
      .catch((err) => setError(describeError(err, '讀取摘要失敗')));
  }, [elderId]);

  const loadPersona = useCallback(() => {
    getPersona(apiConfig, elderId)
      .then(setPersona)
      .catch((err) => setError(describeError(err, '讀取個人化設定失敗')));
  }, [elderId]);

  useEffect(() => {
    if (!config.token) return;
    if (tab === 'events') loadEvents();
    if (tab === 'memories') loadMemories();
    if (tab === 'summaries') loadSummaries();
    if (tab === 'persona') loadPersona();
  }, [tab, config.token, loadEvents, loadMemories, loadSummaries, loadPersona]);

  if (!config.token) {
    return <NotLoggedIn reason="尚未設定登入資訊，請先完成登入設定" />;
  }

  async function handleSaveEvent(eventId: string, eventDate: string, content: string, reviewStatus: ReviewStatus) {
    await updateEvent(apiConfig, eventId, { elderId, eventDate, content, reviewStatus, updatedBy: caregiverId });
    loadEvents();
  }

  async function handlePublishSummary(date: string) {
    await publishSummary(apiConfig, elderId, date);
    loadSummaries();
  }

  async function handleWithdrawSummary(date: string) {
    await withdrawSummary(apiConfig, elderId, date);
    loadSummaries();
  }

  async function handleSavePersona(updates: PersonaContext) {
    const saved = await updatePersona(apiConfig, elderId, { ...updates, updatedBy: caregiverId });
    setPersona(saved);
  }

  return (
    <main style={{ maxWidth: 960, margin: '0 auto', padding: 24 }}>
      <h1 style={{ fontSize: 22, marginBottom: 4 }}>長者詳情</h1>
      <p style={{ color: '#718096', marginBottom: 20 }}>Elder ID: {elderId}</p>

      <div style={{ display: 'flex', gap: 12, marginBottom: 20, borderBottom: '1px solid #e2e8f0' }}>
        {(['events', 'memories', 'summaries', 'persona'] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            style={{
              padding: '8px 16px',
              border: 'none',
              borderBottom: tab === t ? '2px solid #2b6cb0' : '2px solid transparent',
              background: 'none',
              fontWeight: tab === t ? 700 : 400,
              cursor: 'pointer',
            }}
          >
            {t === 'events' ? 'AI 擷取事件' : t === 'memories' ? '記憶管理' : t === 'summaries' ? '每日摘要' : '個人化設定'}
          </button>
        ))}
      </div>

      {error && <p style={{ color: '#e53e3e' }}>{error}</p>}

      {tab === 'events' && (
        <>
          <EventFilterBar filters={eventFilters} onChange={setEventFilters} />
          <EventTable events={events} onSave={handleSaveEvent} />
        </>
      )}

      {tab === 'memories' && (
        <MemoryList
          candidates={memories.candidates}
          confirmed={memories.confirmed}
          onConfirm={async (id) => {
            await confirmMemory(apiConfig, elderId, id, caregiverId);
            loadMemories();
          }}
          onReject={async (id) => {
            await rejectMemory(apiConfig, elderId, id, caregiverId);
            loadMemories();
          }}
          onDelete={async (id) => {
            await deleteMemory(apiConfig, elderId, id);
            loadMemories();
          }}
        />
      )}

      {tab === 'summaries' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {summaries.length === 0 && <p style={{ color: '#718096' }}>目前沒有摘要紀錄。</p>}
          {summaries.map((s) => (
            <div key={s.summaryId} style={{ padding: 12, border: '1px solid #e2e8f0', borderRadius: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <strong>{s.date}</strong>
                <span
                  style={{
                    fontSize: 12,
                    padding: '2px 8px',
                    borderRadius: 999,
                    color: s.status === 'published' ? '#2f855a' : s.status === 'withdrawn' ? '#718096' : '#b7791f',
                    background: s.status === 'published' ? '#f0fff4' : s.status === 'withdrawn' ? '#f7fafc' : '#fffaf0',
                  }}
                >
                  {s.status === 'published' ? '已發布' : s.status === 'withdrawn' ? '已撤回' : '草稿'}
                </span>
              </div>
              <p>{s.content.overview}</p>
              <p style={{ fontSize: 12, color: '#718096' }}>來源事件數：{s.sourceEventIds.length}</p>
              {s.status === 'published' ? (
                <button type="button" onClick={() => handleWithdrawSummary(s.date)}>
                  撤回
                </button>
              ) : (
                <button type="button" onClick={() => handlePublishSummary(s.date)}>
                  發布給家屬
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {tab === 'persona' && <PersonaForm persona={persona} onSave={handleSavePersona} />}
    </main>
  );
}
