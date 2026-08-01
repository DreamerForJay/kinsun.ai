'use client';

import { useEffect, useState } from 'react';
import {
  clearAuthSession,
  createDevelopmentAuthSession,
  hasAuthCredential,
} from '@/lib/auth-session';
import { AUTH_STORAGE_KEYS, clearLegacyBrowserCredential } from '@/lib/runtime-config';

/**
 * Development-only stand-in for the future Cognito authorization-code
 * callback. The submitted token is handed to a same-origin BFF route and then
 * kept only in an HttpOnly cookie; it is never persisted in browser storage.
 */
export default function DevLoginPage() {
  const [token, setToken] = useState('');
  const [elderId, setElderId] = useState('');
  const [caregiverId, setCaregiverId] = useState('');
  const [credentialPresent, setCredentialPresent] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isLocalHost, setIsLocalHost] = useState(false);

  useEffect(() => {
    const host = window.location.hostname.toLowerCase();
    setIsLocalHost(host === 'localhost' || host === '127.0.0.1' || host === '[::1]');
    clearLegacyBrowserCredential();
    setElderId(window.localStorage.getItem(AUTH_STORAGE_KEYS.elderId) ?? '');
    setCaregiverId(window.localStorage.getItem(AUTH_STORAGE_KEYS.caregiverId) ?? '');
    void hasAuthCredential()
      .then(setCredentialPresent)
      .catch(() => setCredentialPresent(null));
  }, []);

  if (process.env.NODE_ENV !== 'development' || !isLocalHost) {
    return (
      <main style={{ maxWidth: 560, margin: '0 auto', padding: 24 }}>
        <h1 style={{ fontSize: 22 }}>本機 Demo 登入</h1>
        <p>這個頁面只可在本機開發環境使用。</p>
        <a href="/sign-in">前往正式登入</a>
      </main>
    );
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!token.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await createDevelopmentAuthSession(token.trim());
      window.localStorage.setItem(AUTH_STORAGE_KEYS.elderId, elderId.trim());
      window.localStorage.setItem(AUTH_STORAGE_KEYS.caregiverId, caregiverId.trim());
      setToken('');
      setCredentialPresent(true);
    } catch {
      setError('無法建立安全登入 Cookie；憑證與目標設定都沒有更新。');
    } finally {
      setBusy(false);
    }
  }

  async function handleClear() {
    setBusy(true);
    setError(null);
    try {
      await clearAuthSession();
      clearLegacyBrowserCredential();
      window.localStorage.removeItem(AUTH_STORAGE_KEYS.elderId);
      window.localStorage.removeItem(AUTH_STORAGE_KEYS.caregiverId);
      setToken('');
      setElderId('');
      setCaregiverId('');
      setCredentialPresent(false);
    } catch {
      setError('登出失敗，安全 Cookie 可能仍存在；請勿將此裝置視為已登出。');
    } finally {
      setBusy(false);
    }
  }

  function loadSyntheticLocalDemo() {
    setToken('local-development-only');
    setElderId('40000000-0000-4000-8000-000000000001');
    setCaregiverId('');
    setError(null);
  }

  return (
    <main style={{ maxWidth: 560, margin: '0 auto', padding: 24 }}>
      <h1 style={{ fontSize: 22, marginBottom: 8 }}>登入設定（Demo 用）</h1>
      <p style={{ color: '#718096', marginBottom: 20, fontSize: 14, lineHeight: 1.6 }}>
        正式 Cognito 尚未串接。本頁只在開發環境建立 HttpOnly Cookie；Token 不會存入
        localStorage，也不會回傳給前端程式。本機 Demo 的 actor 與 tenant 只由 Core API 的
        FAKE_AUTH_* 環境變數決定。請勿使用真實長者資料。
      </p>

      <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <label>
          Bearer Token（本機 Fake Auth 可使用固定測試字串）
          <textarea
            value={token}
            onChange={(e) => setToken(e.target.value)}
            rows={5}
            placeholder="eyJhbGciOi..."
            autoComplete="off"
            spellCheck={false}
            style={{
              display: 'block',
              width: '100%',
              padding: 8,
              marginTop: 4,
              fontFamily: 'monospace',
              fontSize: 12,
            }}
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
          <button type="submit" disabled={busy || !token.trim()}>
            建立安全登入
          </button>
          <button type="button" onClick={loadSyntheticLocalDemo} disabled={busy}>
            載入林阿嬤合成 Demo
          </button>
          <button type="button" onClick={() => void handleClear()} disabled={busy}>
            登出並清除
          </button>
          {credentialPresent === true && (
            <span style={{ color: '#2f855a', fontSize: 14 }}>安全 Cookie 已設定</span>
          )}
          {credentialPresent === false && <span style={{ fontSize: 14 }}>尚未登入</span>}
        </div>
        {error && <p style={{ color: '#c53030', margin: 0 }}>{error}</p>}
      </form>

      <div style={{ marginTop: 24, display: 'flex', gap: 16, fontSize: 14 }}>
        <a href="/">陪伴首頁</a>
        <a href="/dashboard">照護者總覽</a>
        <a href="/family">家屬首頁</a>
      </div>
    </main>
  );
}
