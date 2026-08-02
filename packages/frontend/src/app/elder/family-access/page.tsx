'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { ApiRequestError } from '@/lib/api/client';
import {
  createFamilyInvitation,
  listFamilyInvitations,
  revokeFamilyInvitation,
  type CreatedFamilyInvitation,
  type FamilyInvitationStatus,
} from '@/lib/api/family-invitations';
import { getRuntimeConfig, type RuntimeConfig } from '@/lib/runtime-config';

const STATUS_LABELS: Record<FamilyInvitationStatus['status'], string> = {
  ISSUED: '等待使用',
  REDEEMED: '已使用',
  EXPIRED: '已過期',
  REVOKED: '已撤銷',
  LOCKED: '已鎖定',
};

export default function ElderFamilyAccessPage() {
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const [email, setEmail] = useState('');
  const [invitations, setInvitations] = useState<FamilyInvitationStatus[]>([]);
  const [created, setCreated] = useState<CreatedFamilyInvitation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const apiConfig = useMemo(
    () => ({ apiBaseUrl: config?.apiBaseUrl ?? '/backend/core' }),
    [config?.apiBaseUrl],
  );
  const elderId = config?.elderId ?? '';

  useEffect(() => {
    let cancelled = false;
    void getRuntimeConfig().then((next) => {
      if (!cancelled) setConfig(next);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const reload = useCallback(async () => {
    if (!elderId) return;
    try {
      setInvitations(await listFamilyInvitations(apiConfig, elderId));
    } catch {
      setError('目前無法讀取邀請紀錄，請稍後再試。');
    }
  }, [apiConfig, elderId]);

  useEffect(() => {
    if (config?.credentialStatus === 'present' && elderId) void reload();
  }, [config?.credentialStatus, elderId, reload]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setCreated(null);
    try {
      const result = await createFamilyInvitation(apiConfig, elderId, email.trim() || undefined);
      setCreated(result);
      setEmail('');
      await reload();
    } catch (caught) {
      setError(
        caught instanceof ApiRequestError && caught.status === 409
          ? '建立邀請前，請先在同意設定中開啟「家庭分享」。'
          : '邀請建立失敗，請稍後再試。',
      );
    } finally {
      setBusy(false);
    }
  }

  async function revoke(invitationId: string) {
    setBusy(true);
    setError(null);
    try {
      await revokeFamilyInvitation(apiConfig, elderId, invitationId);
      await reload();
    } catch {
      setError('無法撤銷這組邀請碼，可能已被使用或過期。');
    } finally {
      setBusy(false);
    }
  }

  if (!config) return null;
  if (config.credentialStatus !== 'present' || !elderId) {
    return <NotLoggedIn reason="請先以長者身分登入，再建立家屬邀請碼。" />;
  }

  return (
    <main style={{ margin: '0 auto', maxWidth: 680, padding: 24 }}>
      <h1>家屬分享</h1>
      <p style={{ color: 'var(--color-foreground)', lineHeight: 1.7 }}>
        邀請碼只能使用一次，24 小時後失效。若填寫家屬 Email，只有該 Google 帳號能使用。
      </p>

      <form onSubmit={submit} style={{ margin: '24px 0' }}>
        <label htmlFor="invitee-email" style={{ display: 'block', fontWeight: 700 }}>
          家屬 Email（建議填寫）
        </label>
        <input
          autoComplete="email"
          id="invitee-email"
          onChange={(event) => setEmail(event.target.value)}
          placeholder="family@example.com"
          style={{
            boxSizing: 'border-box',
            fontSize: 18,
            marginTop: 8,
            padding: 12,
            width: '100%',
          }}
          type="email"
          value={email}
        />
        <button
          disabled={busy}
          style={{
            background: 'var(--color-primary)',
            border: 0,
            borderRadius: 10,
            color: 'white',
            fontSize: 18,
            marginTop: 12,
            padding: '14px 18px',
          }}
          type="submit"
        >
          {busy ? '處理中…' : '產生一次性邀請碼'}
        </button>
      </form>

      {created && (
        <section
          aria-live="polite"
          style={{
            background: 'var(--state-confirmed-bg)',
            borderRadius: 'var(--radius-md)',
            padding: 18,
          }}
        >
          <h2 style={{ marginTop: 0 }}>請現在把這組邀請碼交給家屬</h2>
          <p style={{ fontFamily: 'monospace', fontSize: 28, fontWeight: 800, letterSpacing: 2 }}>
            {created.invitation_code}
          </p>
          <p>關閉此畫面後，系統不會再顯示完整邀請碼。</p>
          <button
            onClick={() => void navigator.clipboard.writeText(created.invitation_code)}
            type="button"
          >
            複製邀請碼
          </button>
        </section>
      )}

      {error && (
        <p aria-live="polite" style={{ color: 'var(--color-destructive)' }}>
          {error} <Link href="/consent">前往同意設定</Link>
        </p>
      )}

      <section style={{ marginTop: 30 }}>
        <h2>邀請紀錄</h2>
        {invitations.length === 0 ? (
          <p style={{ color: 'var(--color-foreground)' }}>目前沒有邀請紀錄。</p>
        ) : (
          <ul style={{ listStyle: 'none', padding: 0 }}>
            {invitations.map((item) => (
              <li
                key={item.invitation_id}
                style={{ borderTop: '1px solid var(--color-border)', padding: '14px 0' }}
              >
                <strong>{STATUS_LABELS[item.status]}</strong>
                <span style={{ marginLeft: 12 }}>
                  到期：{new Date(item.expires_at).toLocaleString('zh-TW')}
                </span>
                {item.status === 'ISSUED' && (
                  <button
                    disabled={busy}
                    onClick={() => void revoke(item.invitation_id)}
                    style={{ marginLeft: 12 }}
                    type="button"
                  >
                    撤銷
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <p>
        <Link href="/">返回長者首頁</Link>
      </p>
    </main>
  );
}
