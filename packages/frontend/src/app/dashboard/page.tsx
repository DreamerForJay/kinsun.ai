'use client';

import { useCallback, useEffect, useState } from 'react';
import { ElderOverviewList } from '@/components/dashboard/ElderOverviewList';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { ApiRequestError } from '@/lib/api/client';
import { getCaregiverDashboard, type DashboardElder } from '@/lib/api/dashboard';
import { useLocale } from '@/lib/i18n/locale-context';
import { getRuntimeConfig, type RuntimeConfig } from '@/lib/runtime-config';
import type { MessageKey } from '@/lib/i18n/messages';

export default function CaregiverDashboardPage() {
  const { t } = useLocale();
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const [elders, setElders] = useState<DashboardElder[] | null>(null);
  // Stored as a key, not a rendered string: an error raised before the switch is
  // used must re-render in the new language, not stay frozen in the old one.
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
    if (!config) return;
    setErrorKey(null);
    getCaregiverDashboard(config)
      .then((response) => setElders(response.elders))
      .catch((caught) => {
        setErrorKey(
          caught instanceof ApiRequestError && (caught.status === 403 || caught.status === 404)
            ? 'error.noElderAccess'
            : 'error.reload',
        );
      });
  }, [config]);

  useEffect(() => {
    if (config?.credentialStatus === 'present') load();
  }, [config, load]);

  if (!config) return null;
  if (config.credentialStatus === 'unavailable') {
    return <NotLoggedIn reason={t('auth.credentialUnavailable')} linkLabel={t('common.signIn')} />;
  }
  if (config.credentialStatus !== 'present') {
    return <NotLoggedIn reason={t('auth.credentialMissing')} linkLabel={t('common.signIn')} />;
  }

  return (
    <main style={{ maxWidth: 900, margin: '0 auto', padding: 24 }}>
      <h1 style={{ fontSize: 22, marginBottom: 16 }}>{t('dashboard.title')}</h1>
      <p style={{ color: '#718096', marginBottom: 16 }}>{t('dashboard.subtitle')}</p>
      {errorKey && <p style={{ color: '#e53e3e' }}>{t(errorKey)}</p>}
      {!elders && !errorKey && <p>{t('common.loading')}</p>}
      {elders && <ElderOverviewList elders={elders} />}
    </main>
  );
}
