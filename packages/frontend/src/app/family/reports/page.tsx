'use client';

import { useCallback, useEffect, useState } from 'react';
import type { SummaryRecord } from '@elderly-care/shared';
import Link from 'next/link';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { ApiRequestError } from '@/lib/api/client';
import { listSummaries } from '@/lib/api/summaries';
import { getRuntimeConfig } from '@/lib/runtime-config';

/**
 * 報表中心 (04｜資訊架構、UX 與 User Flow §8.7, §7.3) — full history of
 * published reports. Never shows a transcript, un-reviewed event, ASR
 * confidence, or caregiver-internal note (§8.7); a withdrawn report renders
 * as a placeholder only — the API has already redacted its content.
 */
export default function FamilyReportCenterPage() {
  const config = getRuntimeConfig();
  const apiConfig = { apiBaseUrl: config.apiBaseUrl, token: config.token };
  const elderId = config.elderId;

  const [summaries, setSummaries] = useState<SummaryRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    listSummaries(apiConfig, elderId)
      .then((res) => setSummaries(res.items))
      .catch((err) => {
        setError(
          err instanceof ApiRequestError && err.status === 403
            ? '您目前沒有查看權限，請聯絡照護單位重新授權。'
            : '讀取報表失敗，請重新整理',
        );
      });
  }, [elderId]);

  useEffect(() => {
    if (config.token && elderId) load();
  }, [config.token, elderId, load]);

  if (!config.token || !elderId) {
    return <NotLoggedIn reason="尚未設定登入資訊，請先完成登入設定" />;
  }

  return (
    <main style={{ maxWidth: 720, margin: '0 auto', padding: 24 }}>
      <p style={{ marginBottom: 12 }}>
        <Link href="/family">{'← 返回家屬首頁'}</Link>
      </p>
      <h1 style={{ fontSize: 22, marginBottom: 4 }}>報表中心</h1>
      <p style={{ color: '#718096', marginBottom: 20 }}>歷史每日摘要</p>

      {error && <p style={{ color: '#e53e3e' }}>{error}</p>}
      {!summaries && !error && <p>載入中...</p>}

      {/* No Report (§7.3) */}
      {summaries && summaries.length === 0 && <p style={{ color: '#718096' }}>尚未產生報表。</p>}

      {summaries && summaries.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {summaries.map((s) => (
            <ReportCard key={s.summaryId} summary={s} />
          ))}
        </div>
      )}
    </main>
  );
}

function ReportCard({ summary: s }: { summary: SummaryRecord }) {
  // Withdrawn (§7.3): "顯示此報表已撤回，不保留舊敏感內容" — content is
  // already redacted server-side; render a placeholder, never the fields.
  if (s.status === 'withdrawn') {
    return (
      <div style={{ padding: 16, border: '1px solid #e2e8f0', borderRadius: 8, background: '#f7fafc' }}>
        <strong>{s.date}</strong>
        <p style={{ color: '#718096' }}>此報表已撤回。</p>
      </div>
    );
  }

  // Data Insufficient (§7.3, UX principle #10 無資料就是無資料): no source
  // events means there's nothing real to show — don't render an AI-guessed
  // "content" as if it were a real report.
  const dataInsufficient = s.sourceEventIds.length === 0;

  return (
    <div style={{ padding: 16, border: '1px solid #e2e8f0', borderRadius: 8 }}>
      <strong>{s.date}</strong>
      {dataInsufficient ? (
        <p style={{ color: '#718096' }}>今日資料不足，尚無法產生完整摘要。</p>
      ) : (
        <>
          <p>{s.content.overview}</p>
          {s.content.meals.length > 0 && <p>飲食：{s.content.meals.join('、')}</p>}
          {s.content.activities.length > 0 && <p>活動：{s.content.activities.join('、')}</p>}
          {s.content.sleep && <p>睡眠：{s.content.sleep}</p>}
          {s.content.emotionalState && <p>心情：{s.content.emotionalState}</p>}
        </>
      )}
      <p style={{ fontSize: 12, color: '#718096' }}>
        可追溯來源事件數：{s.sourceEventIds.length}｜發布時間：{s.publishedAt ?? '—'}
      </p>
    </div>
  );
}
