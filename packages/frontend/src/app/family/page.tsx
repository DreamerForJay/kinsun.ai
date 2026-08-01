'use client';

import { useCallback, useEffect, useState } from 'react';
import type { SummaryRecord } from '@elderly-care/shared';
import Link from 'next/link';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { ApiRequestError } from '@/lib/api/client';
import { listSummaries } from '@/lib/api/summaries';
import { getRuntimeConfig } from '@/lib/runtime-config';

const DAY_MS = 24 * 60 * 60 * 1000;

function daysAgoIso(days: number): string {
  return new Date(Date.now() - days * DAY_MS).toISOString().slice(0, 10);
}

/**
 * 家屬首頁 (04｜資訊架構、UX 與 User Flow §8.6) — 頂部長者/最後更新、
 * 今日摘要、本週概覽、最新重要事件，CTA 導向報表中心 (/family/reports)。
 * Only ever reads published (or redacted-withdrawn) summaries — see
 * summaries.ts's family-role filter, never a caregiver's still-draft text.
 */
export default function FamilyHomePage() {
  const config = getRuntimeConfig();
  const apiConfig = { apiBaseUrl: config.apiBaseUrl, token: config.token };
  const elderId = config.elderId;

  const [summaries, setSummaries] = useState<SummaryRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    // 本週概覽 only needs the last 7 days — no reason to pull full history here.
    listSummaries(apiConfig, elderId, { dateFrom: daysAgoIso(7) })
      .then((res) => setSummaries(res.items))
      .catch((err) => {
        if (err instanceof ApiRequestError && err.status === 403) {
          setError('您目前沒有查看權限，請聯絡照護單位重新授權。'); // Authorization Expired (§7.3)
        } else {
          setError('讀取近況失敗，請重新整理');
        }
      });
  }, [elderId]);

  useEffect(() => {
    if (config.token && elderId) load();
  }, [config.token, elderId, load]);

  if (!config.token || !elderId) {
    return <NotLoggedIn reason="尚未設定登入資訊，請先完成登入設定" />;
  }

  if (error) {
    return (
      <main style={{ maxWidth: 720, margin: '0 auto', padding: 24 }}>
        <p style={{ color: '#e53e3e' }}>{error}</p>
      </main>
    );
  }

  if (!summaries) {
    return (
      <main style={{ maxWidth: 720, margin: '0 auto', padding: 24 }}>
        <p>載入中...</p>
      </main>
    );
  }

  const published = summaries.filter((s) => s.status === 'published');
  const today = new Date().toISOString().slice(0, 10);
  const todaySummary = published.find((s) => s.date === today) ?? null;
  const lastUpdated = published.reduce<string | null>((latest, s) => (!latest || s.date > latest ? s.date : latest), null);

  const weekMeals = published.reduce((n, s) => n + s.content.meals.length, 0);
  const weekActivities = published.reduce((n, s) => n + s.content.activities.length, 0);
  const latestImportantEvents = published
    .flatMap((s) => s.content.importantEvents.map((text) => ({ date: s.date, text })))
    .sort((a, b) => b.date.localeCompare(a.date))
    .slice(0, 5);

  return (
    <main style={{ maxWidth: 720, margin: '0 auto', padding: 24 }}>
      {/* 頂部：被授權長者、最後更新與通知入口 */}
      <h1 style={{ fontSize: 22, marginBottom: 4 }}>家屬首頁</h1>
      <p style={{ color: '#718096', marginBottom: 20 }}>
        長者：{elderId}｜最後更新：{lastUpdated ?? '尚無資料'}
      </p>

      {/* 第一區：今日摘要 */}
      <section style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: 16, marginBottom: 8 }}>今日摘要</h2>
        {todaySummary ? (
          todaySummary.sourceEventIds.length === 0 ? (
            <p style={{ color: '#718096' }}>今日資料不足，尚無法產生完整摘要。</p>
          ) : (
            <p>{todaySummary.content.overview}</p>
          )
        ) : (
          <p style={{ color: '#718096' }}>今日尚未產生摘要。</p>
        )}
      </section>

      {/* 第二區：本週概覽 */}
      <section style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: 16, marginBottom: 8 }}>本週概覽</h2>
        {published.length === 0 ? (
          <p style={{ color: '#718096' }}>本週尚無已發布的摘要。</p>
        ) : (
          <p>
            本週已發布 {published.length} 篇摘要，記錄了 {weekMeals} 筆飲食、{weekActivities} 筆活動。
          </p>
        )}
      </section>

      {/* 第三區：最新重要事件 */}
      <section style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: 16, marginBottom: 8 }}>最新重要事件</h2>
        {latestImportantEvents.length === 0 ? (
          <p style={{ color: '#718096' }}>本週尚無重要事件記錄。</p>
        ) : (
          <ul>
            {latestImportantEvents.map((e, i) => (
              <li key={i}>
                {e.date}：{e.text}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* 主要操作：查看完整報表 */}
      <Link href="/family/reports">查看完整報表 →</Link>
    </main>
  );
}
