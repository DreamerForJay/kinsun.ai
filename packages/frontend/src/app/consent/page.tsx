'use client';

import { useEffect, useState } from 'react';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { FamilySharingConsentPanel } from '@/components/FamilySharingConsentPanel';
import { ConsentPanel } from '@/components/voice/ConsentPanel';
import {
  activeBasicVoiceConsent,
  activeFamilySharingConsent,
  listConsents,
  type ConsentRecord,
} from '@/lib/api/consent';
import { getRuntimeConfig, type RuntimeConfig } from '@/lib/runtime-config';

export default function ConsentPage() {
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const [consent, setConsent] = useState<ConsentRecord | null | undefined>(undefined);
  const [familyConsent, setFamilyConsent] = useState<ConsentRecord | null | undefined>(undefined);
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
        if (!cancelled) {
          setConsent(activeBasicVoiceConsent(items));
          setFamilyConsent(activeFamilySharingConsent(items));
        }
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
  if (consent === undefined || familyConsent === undefined)
    return <main style={{ padding: 24 }}>正在向 Core API 查詢同意狀態…</main>;

  return (
    <main style={{ margin: '0 auto', maxWidth: 640, minHeight: '100dvh' }}>
      <ConsentPanel
        apiConfig={config}
        elderId={config.elderId}
        policyVersion={config.consentPolicyVersion}
        initialConsent={consent}
        onChange={setConsent}
      />
      <FamilySharingConsentPanel
        apiConfig={config}
        elderId={config.elderId}
        policyVersion={config.consentPolicyVersion}
        initialConsent={familyConsent}
        onChange={setFamilyConsent}
      />
      <nav style={{ display: 'flex', gap: 16, justifyContent: 'center', padding: 24 }}>
        <a href="/">返回首頁</a>
        <a href="/elder/family-access">管理家屬邀請</a>
      </nav>
    </main>
  );
}
