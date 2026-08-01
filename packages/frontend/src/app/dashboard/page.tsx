'use client';

import { useCallback, useEffect, useState } from 'react';
import { ElderOverviewList } from '@/components/dashboard/ElderOverviewList';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { ApiRequestError } from '@/lib/api/client';
import { getCaregiverDashboard } from '@/lib/api/dashboard';
import { getRuntimeConfig } from '@/lib/runtime-config';
import type { CaregiverDashboardEntry } from '@elderly-care/shared';

export default function CaregiverDashboardPage() {
  const config = getRuntimeConfig();
  const [elders, setElders] = useState<CaregiverDashboardEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    getCaregiverDashboard({ apiBaseUrl: config.apiBaseUrl, token: config.token }, config.caregiverId)
      .then((res) => setElders(res.elders))
      .catch((err) => {
        setError(
          err instanceof ApiRequestError && err.status === 403
            ? '您目前沒有查看權限，請聯絡系統管理員確認照護者身分。'
            : '讀取資料失敗，請重新整理',
        );
      });
  }, [config.apiBaseUrl, config.token, config.caregiverId]);

  useEffect(() => {
    if (config.token && config.caregiverId) load();
  }, [config.token, config.caregiverId, load]);

  if (!config.token || !config.caregiverId) {
    return <NotLoggedIn reason="尚未設定登入資訊，請先完成登入設定" />;
  }

  return (
    <main style={{ maxWidth: 900, margin: '0 auto', padding: 24 }}>
      <h1 style={{ fontSize: 22, marginBottom: 16 }}>照護者總覽</h1>
      {error && <p style={{ color: '#e53e3e' }}>{error}</p>}
      {!elders && !error && <p>載入中...</p>}
      {elders && <ElderOverviewList elders={elders} />}
    </main>
  );
}
