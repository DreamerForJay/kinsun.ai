'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { ApiRequestError } from '@/lib/api/client';
import { listFamilyReports, type FamilyReportView } from '@/lib/api/family-reports';
import { getRuntimeConfig, type RuntimeConfig } from '@/lib/runtime-config';

const REPORT_TYPE_LABEL: Record<FamilyReportView['reportType'], string> = {
  DAILY: '每日報表',
  WEEKLY: '每週報表',
  MONTHLY: '每月報表',
  IMPORTANT_EVENT: '重要事件報表',
};

export default function FamilyReportCenterPage() {
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
            : '讀取報表失敗，請重新整理。',
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

  return (
    <main style={{ maxWidth: 720, margin: '0 auto', padding: 24 }}>
      <p style={{ marginBottom: 12 }}>
        <Link href="/family">← 返回家屬首頁</Link>
      </p>
      <h1 style={{ fontSize: 22, marginBottom: 4 }}>家屬報表中心</h1>
      <p style={{ color: '#718096', marginBottom: 20 }}>
        僅顯示 Core API 依關係授權與發布狀態篩選後的正式內容。
      </p>

      {error && <p style={{ color: '#e53e3e' }}>{error}</p>}
      {!reports && !error && <p>載入中...</p>}
      {reports && reports.length === 0 && (
        <p style={{ color: '#718096' }}>目前沒有可查看的已發布報表。</p>
      )}

      {reports && reports.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {reports.map((report) => (
            <ReportCard key={report.reportId} report={report} />
          ))}
        </div>
      )}
    </main>
  );
}

function ReportCard({ report }: { report: FamilyReportView }) {
  if (report.status === 'WITHDRAWN') {
    return (
      <section
        style={{
          padding: 16,
          border: '1px solid #e2e8f0',
          borderRadius: 8,
          background: '#f7fafc',
        }}
      >
        <strong>
          {report.periodStart}～{report.periodEnd}
        </strong>
        <p style={{ color: '#718096' }}>此報表已撤回。</p>
      </section>
    );
  }

  return (
    <section style={{ padding: 16, border: '1px solid #e2e8f0', borderRadius: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
        <strong>{REPORT_TYPE_LABEL[report.reportType]}</strong>
        <span>
          {report.periodStart}～{report.periodEnd}
        </span>
      </div>
      {report.items.length === 0 ? (
        <p style={{ color: '#718096' }}>{report.dataGapNotice ?? '資料不足。'}</p>
      ) : (
        <ul>
          {report.items.map((item, index) => (
            <li key={`${item.category}-${index}`}>
              [{item.category}] {item.text}（來源 {item.sourceIds.length} 筆）
            </li>
          ))}
        </ul>
      )}
      <p style={{ fontSize: 12, color: '#718096' }}>
        版本 {report.version}｜發布時間：
        {report.publishedAt ? new Date(report.publishedAt).toLocaleString('zh-TW') : '—'}
      </p>
    </section>
  );
}
