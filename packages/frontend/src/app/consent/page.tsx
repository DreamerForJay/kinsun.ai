'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { ConsentPanel } from '@/components/voice/ConsentPanel';
import { activeBasicVoiceConsent, listConsents, type ConsentRecord } from '@/lib/api/consent';
import { getRuntimeConfig, type RuntimeConfig } from '@/lib/runtime-config';

export default function ConsentPage() {
  const router = useRouter();
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const [consent, setConsent] = useState<ConsentRecord | null | undefined>(undefined);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void getRuntimeConfig().then((nextConfig) => {
      if (!cancelled) setConfig(nextConfig);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (config?.credentialStatus !== 'present' || !config.elderId) return;
    let cancelled = false;
    listConsents(config, config.elderId)
      .then((items) => {
        if (!cancelled) setConsent(activeBasicVoiceConsent(items));
      })
      .catch(() => {
        if (!cancelled) setLoadError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [config]);

  if (!config) return null;
  if (config.credentialStatus === 'unavailable') {
    return <NotLoggedIn reason="無法確認登入憑證狀態；系統已停止，不會略過認證" />;
  }
  if (config.credentialStatus !== 'present' || !config.elderId) {
    return <NotLoggedIn reason="尚未設定本機 Demo 身分，請先完成登入設定" />;
  }
  if (loadError) {
    return <NotLoggedIn reason="無法向 Core API 讀取同意狀態；系統已停止，不會推測結果" />;
  }
  if (consent === undefined)
    return <main style={{ padding: 24 }}>正在向 Core API 查詢同意狀態…</main>;

  return (
    <main
      style={{
        minHeight: '100dvh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <ConsentPanel
        apiConfig={config}
        elderId={config.elderId}
        policyVersion={config.consentPolicyVersion}
        initialConsent={consent}
        onChange={(nextConsent) => {
          setConsent(nextConsent);
          if (nextConsent) router.push('/');
        }}
      />
    </main>
  );
}
