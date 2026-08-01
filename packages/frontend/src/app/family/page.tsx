'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { ApiRequestError } from '@/lib/api/client';
import { listFamilyReports, type FamilyReportView } from '@/lib/api/family-reports';
import { getRuntimeConfig, type RuntimeConfig } from '@/lib/runtime-config';

const DAY_MS = 24 * 60 * 60 * 1000;

function daysAgoIso(days: number): string {
  return new Date(Date.now() - days * DAY_MS).toISOString().slice(0, 10);
}

export default function FamilyHomePage() {
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const apiConfig = useMemo(
    () => ({ apiBaseUrl: config?.apiBaseUrl ?? '/backend/core' }),
    [config?.apiBaseUrl],
  );
  const elderId = config?.elderId ?? '';
  const [reports, setReports] = useState<FamilyReportView[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void getRuntimeConfig().then((nextConfig) => {
      if (!cancelled) setConfig(nextConfig);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const load = useCallback(() => {
    setError(null);
    listFamilyReports(apiConfig, elderId)
      .then(setReports)
      .catch((caught) => {
        setError(
          caught instanceof ApiRequestError && (caught.status === 403 || caught.status === 404)
            ? '目前身分沒有查看這位長者家屬報表的權限。'
            : '讀取近況失敗，請重新整理。',
        );
      });
  }, [apiConfig, elderId]);

  useEffect(() => {
    if (config?.credentialStatus === 'present' && elderId) load();
  }, [config?.credentialStatus, elderId, load]);

  if (!config) return null;
  if (config.credentialStatus === 'unavailable') {
    return <NotLoggedIn reason="無法確認登入憑證狀態；系統已停止，不會略過認證" />;
  }
  if (config.credentialStatus !== 'present' || !elderId) {
    return <NotLoggedIn reason="尚未設定登入資訊，請先完成登入設定" />;
  }

  if (error) {
    return (
      <main style={{ maxWidth: 720, margin: '0 auto', padding: 24 }}>
        <p style={{ color: '#e53e3e' }}>{error}</p>
      </main>
    );
  }

  if (!reports) {
    return (
      <main style={{ maxWidth: 720, margin: '0 auto', padding: 24 }}>
        <p>載入中...</p>
      </main>
    );
  }

  const published = reports.filter((report) => report.status === 'PUBLISHED');
  const weekStart = daysAgoIso(7);
  const weeklyReports = published.filter((report) => report.periodEnd >= weekStart);
  const today = new Date().toISOString().slice(0, 10);
  const todayReport =
    published.find(
      (report) =>
        report.reportType === 'DAILY' && report.periodStart <= today && report.periodEnd >= today,
    ) ?? null;
  const lastUpdated = published.reduce<string | null>(
    (latest, report) => (!latest || report.updatedAt > latest ? report.updatedAt : latest),
    null,
  );
  const mealCount = weeklyReports.reduce(
    (count, report) =>
      count + report.items.filter((item) => item.category.toUpperCase() === 'MEAL').length,
    0,
  );
  const activityCount = weeklyReports.reduce(
    (count, report) =>
      count + report.items.filter((item) => item.category.toUpperCase() === 'ACTIVITY').length,
    0,
  );
  const importantItems = weeklyReports
    .flatMap((report) =>
      report.items
        .filter((item) => item.category.toUpperCase() === 'IMPORTANT_EVENT')
        .map((item) => ({ date: report.periodEnd, text: item.text })),
    )
    .sort((left, right) => right.date.localeCompare(left.date))
    .slice(0, 5);

  return (
    <main style={{ maxWidth: 720, margin: '0 auto', padding: 24 }}>
      <h1 style={{ fontSize: 22, marginBottom: 4 }}>家屬首頁</h1>
      <p style={{ color: '#718096', marginBottom: 20 }}>
        長者：{elderId}｜最後更新：
        {lastUpdated ? new Date(lastUpdated).toLocaleString('zh-TW') : '尚無資料'}
      </p>

      <section style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: 16, marginBottom: 8 }}>今日報表</h2>
        {todayReport ? (
          todayReport.items.length > 0 ? (
            <ul>
              {todayReport.items.map((item, index) => (
                <li key={`${item.category}-${index}`}>{item.text}</li>
              ))}
            </ul>
          ) : (
            <p style={{ color: '#718096' }}>{todayReport.dataGapNotice ?? '今日資料不足。'}</p>
          )
        ) : (
          <p style={{ color: '#718096' }}>今日尚無已發布的家屬報表。</p>
        )}
      </section>

      <section style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: 16, marginBottom: 8 }}>本週概覽</h2>
        {weeklyReports.length === 0 ? (
          <p style={{ color: '#718096' }}>本週尚無已發布的家屬報表。</p>
        ) : (
          <p>
            本週有 {weeklyReports.length} 份正式報表，包含 {mealCount} 筆飲食與 {activityCount}{' '}
            筆活動項目。
          </p>
        )}
      </section>

      <section style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: 16, marginBottom: 8 }}>最新重要事件</h2>
        {importantItems.length === 0 ? (
          <p style={{ color: '#718096' }}>本週沒有可分享的重要事件。</p>
        ) : (
          <ul>
            {importantItems.map((item, index) => (
              <li key={`${item.date}-${index}`}>
                {item.date}：{item.text}
              </li>
            ))}
          </ul>
        )}
      </section>

      <Link href="/family/reports">查看完整報表 →</Link>
    </main>
  );
}
