'use client';

import { useEffect, useState } from 'react';

type SignInMethodStatus = {
  googleLinked: boolean;
  lineLinked: boolean;
  lineLoginEnabled: boolean;
};

export function SignInMethodsClient() {
  const [status, setStatus] = useState<SignInMethodStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void fetch('/backend/auth/identities', {
      cache: 'no-store',
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    })
      .then(async (response) => {
        if (response.status === 401) throw new Error('AUTHENTICATION_REQUIRED');
        if (!response.ok) throw new Error('UNAVAILABLE');
        const payload = (await response.json()) as { data?: Partial<SignInMethodStatus> };
        if (
          typeof payload.data?.googleLinked !== 'boolean' ||
          typeof payload.data.lineLinked !== 'boolean' ||
          typeof payload.data.lineLoginEnabled !== 'boolean'
        ) {
          throw new Error('UNAVAILABLE');
        }
        if (!cancelled) setStatus(payload.data as SignInMethodStatus);
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setError(
          reason instanceof Error && reason.message === 'AUTHENTICATION_REQUIRED'
            ? '登入狀態已失效，請先重新登入。'
            : '目前無法確認登入方式，請稍後再試。',
        );
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <div>
        <p role="alert" style={{ color: 'var(--color-destructive)' }}>
          {error}
        </p>
        <a href="/sign-in">前往登入</a>
      </div>
    );
  }
  if (!status) return <p>正在確認已連結的登入方式…</p>;

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <section style={{ border: '1px solid var(--color-border-strong)', borderRadius: 12, padding: 18 }}>
        <h2 style={{ fontSize: 20, marginTop: 0 }}>Google</h2>
        <p style={{ marginBottom: 0 }}>{status.googleLinked ? '已連結' : '未連結'}</p>
      </section>
      <section style={{ border: '1px solid var(--color-border-strong)', borderRadius: 12, padding: 18 }}>
        <h2 style={{ fontSize: 20, marginTop: 0 }}>LINE Login</h2>
        <p>{status.lineLinked ? '已連結' : '未連結'}</p>
        {!status.lineLoginEnabled && <p>目前環境尚未啟用 LINE Login。</p>}
        {status.lineLoginEnabled && !status.lineLinked && (
          <form action="/backend/auth/identities/line/start" method="post">
            <button
              disabled={!status.googleLinked}
              style={{
                background: status.googleLinked ? 'var(--color-accent)' : 'var(--color-muted-foreground)',
                border: 0,
                borderRadius: 8,
                color: 'white',
                cursor: status.googleLinked ? 'pointer' : 'not-allowed',
                fontSize: 17,
                padding: '12px 16px',
              }}
              type="submit"
            >
              新增 LINE 登入
            </button>
          </form>
        )}
        {status.lineLoginEnabled && !status.googleLinked && !status.lineLinked && (
          <p>請先使用已連結的 Google 帳號登入，再新增 LINE Login。</p>
        )}
      </section>
    </div>
  );
}
