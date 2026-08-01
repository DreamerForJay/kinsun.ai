'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { familyReportState, StateCard } from '@/components/StateCard';
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

  const period = t('reports.period', { start: report.periodStart, end: report.periodEnd });
  const title = t(`reportType.${report.reportType}` as MessageKey);
  const meta = (
    <>
      {period}
      {report.status !== 'WITHDRAWN' &&
        ` ｜ ${t('reports.publishedAt', {
          version: report.version,
          at: formatDateTime(report.publishedAt),
        })}`}
    </>
  );

  if (report.status === 'WITHDRAWN') {
    // §10.3 / §4.2: struck-through title, and none of the old content — a
    // withdrawn report keeps no items, not even collapsed.
    return (
      <StateCard state="withdrawn" title={title} meta={meta}>
        {t('reports.withdrawn')}
      </StateCard>
    );
  }

  // "No data" is a first-class state with its own shape (§1, §4.2), not an
  // empty card. `dataGapNotice` is Core-authored prose, shown as-is when present.
  if (report.items.length === 0) {
    return (
      <StateCard state="dataInsufficient" title={title} meta={meta}>
        {report.dataGapNotice ?? t('reports.insufficient')}
      </StateCard>
    );
  }

  return (
    <StateCard state={familyReportState(report.status)} title={title} meta={meta}>
      <ul style={{ margin: 0, paddingInlineStart: 'var(--space-5)' }}>
        {report.items.map((item, index) => (
          <li key={`${item.category}-${index}`}>
            [{item.category}] {item.text}
            {t('common.sources', { count: item.sourceIds.length })}
          </li>
        ))}
      </ul>
    </StateCard>
  );
}
