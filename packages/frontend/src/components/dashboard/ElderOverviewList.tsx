'use client';

import Link from 'next/link';
import type { DashboardElder } from '@/lib/api/dashboard';
import { useLocale } from '@/lib/i18n/locale-context';

export interface ElderOverviewListProps {
  elders: DashboardElder[];
}

export function ElderOverviewList({ elders }: ElderOverviewListProps) {
  const { t } = useLocale();

  if (elders.length === 0) {
    return <p style={{ color: 'var(--color-muted-foreground)' }}>{t('dashboard.empty')}</p>;
  }

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <thead>
        <tr style={{ textAlign: 'left', borderBottom: '2px solid var(--color-border-strong)' }}>
          <th style={{ padding: 8 }}>{t('dashboard.colElder')}</th>
          <th style={{ padding: 8 }}>{t('dashboard.colCareUnit')}</th>
          <th style={{ padding: 8 }}>{t('dashboard.colAuthorization')}</th>
        </tr>
      </thead>
      <tbody>
        {elders.map((elder) => (
          <tr key={elder.elderId} style={{ borderBottom: '1px solid var(--color-border)' }}>
            <td style={{ padding: 8 }}>
              <Link
                href={`/dashboard/${elder.elderId}`}
                style={{ color: 'var(--color-primary-text)' }}
              >
                {elder.elderName}
              </Link>
            </td>
            <td style={{ padding: 8 }}>{elder.careUnitName ?? t('common.empty')}</td>
            {/* `authorizationSummary` is prose from the Core API and is not
                translated here — it is data, not UI copy. */}
            <td style={{ padding: 8 }}>
              {elder.authorizationSummary ?? t('dashboard.authorized')}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
