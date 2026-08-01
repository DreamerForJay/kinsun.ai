'use client';

import { useEffect, useState } from 'react';
import { AUTH_STORAGE_KEYS } from '@/lib/runtime-config';

/**
 * Stand-in for Cognito Hosted UI sign-in, which isn't built (see
 * runtime-config.ts). Every other page reads token/elderId/caregiverId
 * straight out of localStorage — this is the only page that writes them.
 * Paste a real ID token for a seeded demo/test Cognito account (never a
 * real elder's identifiers — 競賽個資規則禁止使用真實長者個資).
 */
export default function DevLoginPage() {
  const [token, setToken] = useState('');
  const [elderId, setElderId] = useState('');
  const [caregiverId, setCaregiverId] = useState('');
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setToken(window.localStorage.getItem(AUTH_STORAGE_KEYS.token) ?? '');
    setElderId(window.localStorage.getItem(AUTH_STORAGE_KEYS.elderId) ?? '');
    setCaregiverId(window.localStorage.getItem(AUTH_STORAGE_KEYS.caregiverId) ?? '');
  }, []);

  function handleSave(e: React.FormEvent) {
    e.preventDefault();
    window.localStorage.setItem(AUTH_STORAGE_KEYS.token, token.trim());
    window.localStorage.setItem(AUTH_STORAGE_KEYS.elderId, elderId.trim());
    window.localStorage.setItem(AUTH_STORAGE_KEYS.caregiverId, caregiverId.trim());
    setSaved(true);
  }

  function handleClear() {
    window.localStorage.removeItem(AUTH_STORAGE_KEYS.token);
    window.localStorage.removeItem(AUTH_STORAGE_KEYS.elderId);
    window.localStorage.removeItem(AUTH_STORAGE_KEYS.caregiverId);
    window.localStorage.removeItem(AUTH_STORAGE_KEYS.consentGranted);
    setToken('');
    setElderId('');
    setCaregiverId('');
    setSaved(false);
  }

  return (
    <main style={{ maxWidth: 560, margin: '0 auto', padding: 24 }}>
      <h1 style={{ fontSize: 22, marginBottom: 8 }}>登入設定（Demo 用）</h1>
      <p style={{ color: '#718096', marginBottom: 20, fontSize: 14, lineHeight: 1.6 }}>
        系統還沒有正式的登入畫面（Cognito Hosted UI 尚未串接）。請貼上一組測試帳號的 Cognito ID
        Token（由有 AWS 權限的人在 Cognito 建立模擬帳號後換發），以及要用哪個長者/照護者身分操作。
        請勿使用真實長者的個資。
      </p>

      <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <label>
          Cognito ID Token
          <textarea
            value={token}
            onChange={(e) => setToken(e.target.value)}
            rows={5}
            placeholder="eyJhbGciOi..."
            style={{ display: 'block', width: '100%', padding: 8, marginTop: 4, fontFamily: 'monospace', fontSize: 12 }}
          />
        </label>

        <label>
          Elder ID
          <input
            type="text"
            value={elderId}
            onChange={(e) => setElderId(e.target.value)}
            placeholder="elder 角色本人，或家屬/照護者要查看的長者 ID"
            style={{ display: 'block', width: '100%', padding: 8, marginTop: 4 }}
          />
        </label>

        <label>
          Caregiver ID（僅照護者總覽 /dashboard 需要）
          <input
            type="text"
            value={caregiverId}
            onChange={(e) => setCaregiverId(e.target.value)}
            placeholder="caregiver 角色才需要填"
            style={{ display: 'block', width: '100%', padding: 8, marginTop: 4 }}
          />
        </label>

        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <button type="submit">儲存</button>
          <button type="button" onClick={handleClear}>
            清除全部
          </button>
          {saved && <span style={{ color: '#2f855a', fontSize: 14 }}>已儲存</span>}
        </div>
      </form>

      <div style={{ marginTop: 24, display: 'flex', gap: 16, fontSize: 14 }}>
        <a href="/">語音首頁</a>
        <a href="/dashboard">照護者總覽</a>
        <a href="/family">家屬首頁</a>
      </div>
    </main>
  );
}
