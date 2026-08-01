'use client';

import { useCallback, useEffect, useState } from 'react';
import { ElderOverviewList } from '@/components/dashboard/ElderOverviewList';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { ApiRequestError } from '@/lib/api/client';
import { getCaregiverDashboard, type DashboardElder } from '@/lib/api/dashboard';
import { getRuntimeConfig, type RuntimeConfig } from '@/lib/runtime-config';

export default function CaregiverDashboardPage() {
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const [elders, setElders] = useState<DashboardElder[] | null>(null);
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
    if (!config) return;
    setError(null);
    getCaregiverDashboard(config)
      .then((response) => setElders(response.elders))
      .catch((caught) => {
        setError(
          caught instanceof ApiRequestError && (caught.status === 403 || caught.status === 404)
            ? '目前身分沒有可查看的長者資料，請確認後端授權設定。'
            : '讀取資料失敗，請重新整理。',
        );
      });
  }, [config]);

  useEffect(() => {
    if (config?.credentialStatus === 'present') load();
  }, [config, load]);

  if (!config) return null;
  if (config.credentialStatus === 'unavailable') {
    return <NotLoggedIn reason="無法確認登入憑證狀態；系統已停止，不會略過認證" />;
  }
  if (config.credentialStatus !== 'present') {
    return <NotLoggedIn reason="尚未設定登入資訊，請先完成登入設定" />;
  }

  return (
    <main style={{ maxWidth: 900, margin: '0 auto', padding: 24 }}>
      <h1 style={{ fontSize: 22, marginBottom: 16 }}>授權長者總覽</h1>
      <p style={{ color: '#718096', marginBottom: 16 }}>
        清單由 Core API 依目前登入身分與正式授權關係產生。
      </p>
      {error && <p style={{ color: '#e53e3e' }}>{error}</p>}
      {!elders && !error && <p>載入中...</p>}
      {elders && <ElderOverviewList elders={elders} />}
    </main>
  );
}
