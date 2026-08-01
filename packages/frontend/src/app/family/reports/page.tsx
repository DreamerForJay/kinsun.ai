'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { ApiRequestError } from '@/lib/api/client';
import { listFamilyReports, type FamilyReportView } from '@/lib/api/family-reports';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';
import { getRuntimeConfig, type RuntimeConfig } from '@/lib/runtime-config';

export default function FamilyReportCenterPage() {
  const { t } = useLocale();
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const apiConfig = useMemo(
    () => ({ apiBaseUrl: config?.apiBaseUrl ?? '/backend/core' }),
    [config?.apiBaseUrl],
  );
  const elderId = config?.elderId ?? '';
  const [reports, setReports] = useState<FamilyReportView[] | null>(null);
  const [errorKey, setErrorKey] = useState<MessageKey | null>(null);

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
    setErrorKey(null);
    listFamilyReports(apiConfig, elderId)
      .then(setReports)
      .catch((caught) => {
        setErrorKey(
          caught instanceof ApiRequestError && (caught.status === 403 || caught.status === 404)
            ? 'error.noFamilyReportAccess'
            : 'error.loadReportsFailed',
        );
      });
  }, [apiConfig, elderId]);

  useEffect(() => {
    if (config?.credentialStatus === 'present' && elderId) load();
  }, [config?.credentialStatus, elderId, load]);

  if (!config) return null;
  if (config.credentialStatus === 'unavailable') {
    return <NotLoggedIn reason={t('auth.credentialUnavailable')} linkLabel={t('common.signIn')} />;
  }
  if (config.credentialStatus !== 'present' || !elderId) {
    return <NotLoggedIn reason={t('auth.credentialMissing')} linkLabel={t('common.signIn')} />;
  }

  return (
    <main style={{ maxWidth: 720, margin: '0 auto', padding: 24 }}>
      <p style={{ marginBottom: 12 }}>
        <Link href="/family">{t('reports.back')}</Link>
      </p>
      <h1 style={{ fontSize: 22, marginBottom: 4 }}>{t('reports.title')}</h1>
      <p style={{ color: '#718096', marginBottom: 20 }}>{t('reports.subtitle')}</p>

      {errorKey && <p style={{ color: '#e53e3e' }}>{t(errorKey)}</p>}
      {!reports && !errorKey && <p>{t('common.loading')}</p>}
      {reports && reports.length === 0 && <p style={{ color: '#718096' }}>{t('reports.empty')}</p>}

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
  const { t, formatDateTime } = useLocale();

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
        {/* Withdrawn keeps no old content — MASTER.md §10.3. */}
        <p style={{ color: '#718096' }}>{t('reports.withdrawn')}</p>
      </section>
    );
  }

  return (
    <section style={{ padding: 16, border: '1px solid #e2e8f0', borderRadius: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
        <strong>{t(`reportType.${report.reportType}` as MessageKey)}</strong>
        <span>
          {report.periodStart}～{report.periodEnd}
        </span>
      </div>
      {report.items.length === 0 ? (
        <p style={{ color: '#718096' }}>{report.dataGapNotice ?? t('reports.insufficient')}</p>
      ) : (
        <ul>
          {report.items.map((item, index) => (
            <li key={`${item.category}-${index}`}>
              [{item.category}] {item.text}
              {t('common.sources', { count: item.sourceIds.length })}
            </li>
          ))}
        </ul>
      )}
      <p style={{ fontSize: 12, color: '#718096' }}>
        {t('reports.publishedAt', {
          version: report.version,
          at: formatDateTime(report.publishedAt),
        })}
      </p>
    </section>
  );
}
