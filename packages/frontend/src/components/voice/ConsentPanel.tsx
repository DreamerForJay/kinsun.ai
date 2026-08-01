'use client';

import { useState } from 'react';
import { ApiRequestError } from '@/lib/api/client';
import {
  grantBasicVoiceConsent,
  revokeBasicVoiceConsent,
  type ConsentApiConfig,
  type ConsentRecord,
} from '@/lib/api/consent';

function describeConsentError(error: unknown): string {
  if (error instanceof ApiRequestError && error.status === 404) {
    return '目前無法設定這位長者的同意，請確認身分與授權範圍。';
  }
  if (error instanceof ApiRequestError && error.status === 409) {
    return '同意狀態剛剛已變更，請重新整理後再試。';
  }
  return '設定失敗，請稍後再試。';
}

export interface ConsentPanelProps {
  apiConfig: ConsentApiConfig;
  elderId: string;
  policyVersion: string;
  initialConsent: ConsentRecord | null;
  onChange: (consent: ConsentRecord | null) => void;
}

export function ConsentPanel({
  apiConfig,
  elderId,
  policyVersion,
  initialConsent,
  onChange,
}: ConsentPanelProps) {
  const [consent, setConsent] = useState(initialConsent);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleGrant() {
    if (!policyVersion) return;
    setBusy(true);
    setError(null);
    try {
      const next = await grantBasicVoiceConsent(apiConfig, elderId, policyVersion);
      setConsent(next);
      onChange(next);
    } catch (err) {
      setError(describeConsentError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleRevoke() {
    if (!consent) return;
    setBusy(true);
    setError(null);
    try {
      await revokeBasicVoiceConsent(apiConfig, elderId, consent.consent_id);
      setConsent(null);
      onChange(null);
    } catch (err) {
      setError(describeConsentError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ maxWidth: 560, margin: '0 auto', padding: 24, fontSize: 18, lineHeight: 1.7 }}>
      <h1 style={{ fontSize: 24, marginBottom: 16 }}>文字陪伴同意說明</h1>
      <p>本階段取得的是獨立的 BASIC_VOICE 陪伴同意，用來建立受控 Session 並產生安全回覆。</p>
      <ul>
        <li>目前只會送出您主動輸入的文字，不會開啟麥克風或上傳音訊。</li>
        <li>本輪文字不會自動成為長期記憶、照護事件或逐字稿。</li>
        <li>每次互動前，Core 都會重新檢查身分、長者範圍及同意版本。</li>
      </ul>
      <p>您可以隨時撤回；撤回後，新的陪伴 Session 會立即被 Core 拒絕。</p>

      {!consent && !policyVersion && (
        <p style={{ color: 'var(--color-destructive)' }}>
          尚未設定同意政策版本，為避免套用錯誤政策，目前不能建立同意。
        </p>
      )}

      <div style={{ marginTop: 24, display: 'flex', gap: 12, justifyContent: 'center' }}>
        {consent ? (
          <button type="button" onClick={handleRevoke} disabled={busy}>
            撤回陪伴同意
          </button>
        ) : (
          <button type="button" onClick={handleGrant} disabled={busy || !policyVersion}>
            我同意，開始文字陪伴
          </button>
        )}
      </div>

      <p style={{ marginTop: 12, textAlign: 'center' }}>
        Core API 目前狀態：{consent ? `已同意（版本 ${consent.consent_version}）` : '尚未同意'}
      </p>
      {error && <p style={{ color: 'var(--color-destructive)', textAlign: 'center' }}>{error}</p>}
    </div>
  );
}
