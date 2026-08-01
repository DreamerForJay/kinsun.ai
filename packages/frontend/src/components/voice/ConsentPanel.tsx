'use client';

import { useState } from 'react';
import { ApiRequestError } from '@/lib/api/client';
import { grantConsent, revokeConsent, type ConsentApiConfig } from '@/lib/api/consent';

function describeConsentError(err: unknown): string {
  if (err instanceof ApiRequestError && err.status === 403) {
    return '您目前沒有權限設定這位長者的錄音同意，請聯絡照護單位確認身分。';
  }
  return '設定失敗，請稍後再試';
}

export interface ConsentPanelProps {
  apiConfig: ConsentApiConfig;
  elderId: string;
  initialGranted: boolean;
  onChange: (granted: boolean) => void;
}

/** Consent explanation + grant/revoke flow (A06.1-A06.4). */
export function ConsentPanel({ apiConfig, elderId, initialGranted, onChange }: ConsentPanelProps) {
  const [granted, setGranted] = useState(initialGranted);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleGrant() {
    setBusy(true);
    setError(null);
    try {
      await grantConsent(apiConfig, elderId);
      setGranted(true);
      onChange(true);
    } catch (err) {
      setError(describeConsentError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleRevoke() {
    setBusy(true);
    setError(null);
    try {
      await revokeConsent(apiConfig, elderId);
      setGranted(false);
      onChange(false);
    } catch (err) {
      setError(describeConsentError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ maxWidth: 480, margin: '0 auto', padding: 24, fontSize: 18, lineHeight: 1.7 }}>
      <h1 style={{ fontSize: 22, marginBottom: 16 }}>錄音與資料使用說明</h1>
      <p>當您按下錄音按鈕說話時，系統會錄下您說的話，用來：</p>
      <ul>
        <li>了解您說的內容，給您回覆</li>
        <li>整理您的生活紀錄（例如吃飯、睡覺、活動），提供給照顧您的人參考</li>
      </ul>
      <p>語音檔案會保存 90 天後自動刪除。您可以隨時要求刪除或更正您的資料。</p>
      <p>您可以隨時撤回這個同意，撤回後系統就不會再錄音。</p>

      <div style={{ marginTop: 24, display: 'flex', gap: 12, justifyContent: 'center' }}>
        {granted ? (
          <button
            type="button"
            onClick={handleRevoke}
            disabled={busy}
            style={{ padding: '12px 28px', fontSize: 18, borderRadius: 8, border: '1px solid #e53e3e', background: '#fff', color: '#e53e3e' }}
          >
            撤回同意
          </button>
        ) : (
          <button
            type="button"
            onClick={handleGrant}
            disabled={busy}
            style={{ padding: '12px 28px', fontSize: 18, borderRadius: 8, border: 'none', background: '#2b6cb0', color: '#fff' }}
          >
            我同意，開始使用
          </button>
        )}
      </div>

      <p style={{ marginTop: 12, textAlign: 'center', color: granted ? '#38a169' : '#a0aec0' }}>
        目前狀態：{granted ? '已同意錄音' : '尚未同意錄音'}
      </p>
      {error && <p style={{ color: '#e53e3e', textAlign: 'center' }}>{error}</p>}
    </div>
  );
}
