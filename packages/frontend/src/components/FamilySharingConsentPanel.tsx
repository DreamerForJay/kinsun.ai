'use client';

import { useState } from 'react';
import { ApiRequestError, type ApiConfig } from '@/lib/api/client';
import {
  grantFamilySharingConsent,
  revokeFamilySharingConsent,
  type ConsentRecord,
} from '@/lib/api/consent';

interface FamilySharingConsentPanelProps {
  apiConfig: ApiConfig;
  elderId: string;
  policyVersion: string;
  initialConsent: ConsentRecord | null;
  onChange: (consent: ConsentRecord | null) => void;
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiRequestError && error.status === 404) {
    return '目前無法設定家庭分享，請確認登入身分與長者範圍。';
  }
  if (error instanceof ApiRequestError && error.status === 409) {
    return '同意狀態剛剛已變更，請重新整理後再試。';
  }
  return '設定失敗，請稍後再試。';
}

export function FamilySharingConsentPanel({
  apiConfig,
  elderId,
  policyVersion,
  initialConsent,
  onChange,
}: FamilySharingConsentPanelProps) {
  const [consent, setConsent] = useState(initialConsent);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function grant() {
    if (!policyVersion) return;
    setBusy(true);
    setError(null);
    try {
      const next = await grantFamilySharingConsent(apiConfig, elderId, policyVersion);
      setConsent(next);
      onChange(next);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function revoke() {
    if (!consent) return;
    setBusy(true);
    setError(null);
    try {
      await revokeFamilySharingConsent(apiConfig, elderId, consent.consent_id);
      setConsent(null);
      onChange(null);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section style={{ borderTop: '1px solid #d1d5db', maxWidth: 560, padding: 24 }}>
      <h2>家屬分享同意</h2>
      <p>
        開啟後，您才可以產生一次性邀請碼。家屬只能讀取您選定的正式家庭報表，不能查看逐字稿、記憶或其他長者資料。
      </p>
      <ul>
        <li>每組邀請碼只能使用一次，且預設 24 小時失效。</li>
        <li>Core 每次讀取報表都會重新確認同意與家屬關係。</li>
        <li>撤回後，新的家屬報表讀取會立即被拒絕。</li>
      </ul>
      {!policyVersion && !consent && <p>尚未設定同意政策版本，目前不能開啟家庭分享。</p>}
      {consent ? (
        <button disabled={busy} onClick={() => void revoke()} type="button">
          撤回家庭分享同意
        </button>
      ) : (
        <button disabled={busy || !policyVersion} onClick={() => void grant()} type="button">
          我同意開啟家庭分享
        </button>
      )}
      <p>目前狀態：{consent ? `已同意（版本 ${consent.consent_version}）` : '尚未同意'}</p>
      {error && <p style={{ color: 'var(--color-destructive)' }}>{error}</p>}
    </section>
  );
}
