'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { StateCard } from '@/components/StateCard';
import { ApiRequestError } from '@/lib/api/client';
import { listFamilyReports, type FamilyReportView } from '@/lib/api/family-reports';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';
import { getRuntimeConfig, type RuntimeConfig } from '@/lib/runtime-config';

const DAY_MS = 24 * 60 * 60 * 1000;

function daysAgoIso(days: number): string {
  return new Date(Date.now() - days * DAY_MS).toISOString().slice(0, 10);
}

export default function FamilyHomePage() {
  const { t, formatDateTime } = useLocale();
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
            : 'error.loadRecentFailed',
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

  if (errorKey) {
    return (
      <main style={{ maxWidth: 720, margin: '0 auto', padding: 24 }}>
        <p style={{ color: 'var(--color-destructive)' }}>{t(errorKey)}</p>
      </main>
    );
  }

  if (!reports) {
    return (
      <main style={{ maxWidth: 720, margin: '0 auto', padding: 24 }}>
        <p>{t('common.loading')}</p>
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
      <h1 style={{ fontSize: 22, marginBottom: 4 }}>{t('family.homeTitle')}</h1>
      <p style={{ color: 'var(--color-muted-foreground)', marginBottom: 20 }}>
        {t('family.meta', {
          elderId,
          updated: lastUpdated ? formatDateTime(lastUpdated) : t('family.noData'),
        })}
      </p>

      <section style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: 16, marginBottom: 8 }}>{t('family.todayTitle')}</h2>
        {todayReport ? (
          todayReport.items.length > 0 ? (
            <ul>
              {todayReport.items.map((item, index) => (
                <li key={`${item.category}-${index}`}>{item.text}</li>
              ))}
            </ul>
          ) : (
            /* §1 / §4.2: "no data" gets its own shape rather than a grey line of
               text, so it never reads as a section that failed to load.
               `dataGapNotice` is Core-authored prose, not UI copy — shown as-is
               when present rather than replaced by a translated string. */
            <StateCard state="dataInsufficient">
              {todayReport.dataGapNotice ?? t('family.todayInsufficient')}
            </StateCard>
          )
        ) : (
          <StateCard state="dataInsufficient">{t('family.todayNone')}</StateCard>
        )}
      </section>

      <section style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: 16, marginBottom: 8 }}>{t('family.weekTitle')}</h2>
        {weeklyReports.length === 0 ? (
          <p style={{ color: 'var(--color-muted-foreground)' }}>{t('family.weekNone')}</p>
        ) : (
          <p>
            {t('family.weekSummary', {
              reports: weeklyReports.length,
              meals: mealCount,
              activities: activityCount,
            })}
          </p>
        )}
      </section>

      <section style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: 16, marginBottom: 8 }}>{t('family.importantTitle')}</h2>
        {importantItems.length === 0 ? (
          <p style={{ color: 'var(--color-muted-foreground)' }}>{t('family.importantNone')}</p>
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

      <Link href="/family/reports">{t('family.viewAll')}</Link>
    </main>
  );
}
