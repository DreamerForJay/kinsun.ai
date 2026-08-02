export const dynamic = 'force-dynamic';

import { touchLinkStyle } from '@/components/touch-link';

export default function ElderStartPage() {
  const showLine = process.env.LINE_LOGIN_ENABLED?.trim().toLowerCase() === 'true';
  return (
    <main
      style={{
        margin: '0 auto',
        maxWidth: 640,
        padding: 'var(--space-6)',
        paddingBottom: 'calc(var(--space-6) + env(safe-area-inset-bottom))',
        textAlign: 'center',
      }}
    >
      <h1 style={{ fontSize: 'var(--text-2xl)', lineHeight: 1.4 }}>準備好和小暖說說話了嗎？</h1>
      <p
        style={{
          color: 'var(--color-foreground)',
          fontSize: 'var(--text-base)',
          lineHeight: 'var(--leading-body)',
          margin: 'var(--space-6) 0',
        }}
      >
        請用 Google 帳號登入。完成後，我們會帶您回到這裡開始使用。
      </p>
      <form action="/backend/auth/login" method="post">
        <input name="intent" type="hidden" value="ELDER" />
        <input name="provider" type="hidden" value="GOOGLE" />
        <input name="returnTo" type="hidden" value="/onboarding/resolve" />
        {/* §6.1 — 64px is the elder-surface minimum, and it comes from
            --touch-min rather than a hardcoded height so a 200% system font
            size grows the control instead of clipping it (§5.1). */}
        <button
          style={{
            background: 'var(--color-primary)',
            border: 0,
            borderRadius: 'var(--radius-md)',
            color: 'var(--color-on-primary)',
            cursor: 'pointer',
            display: 'block',
            fontSize: 'var(--text-lg)',
            minHeight: 'var(--touch-min)',
            padding: 'var(--space-4) var(--space-5)',
            width: '100%',
          }}
          type="submit"
        >
          使用 Google 繼續
        </button>
      </form>
      {showLine && (
        <form action="/backend/auth/login" method="post" style={{ marginTop: 'var(--space-3)' }}>
          <input name="intent" type="hidden" value="ELDER" />
          <input name="provider" type="hidden" value="LINE" />
          <input name="returnTo" type="hidden" value="/onboarding/resolve" />
          <button
            style={{
              background: 'var(--color-surface)',
              border: '1px solid var(--color-border-strong)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--color-primary-text)',
              cursor: 'pointer',
              display: 'block',
              fontSize: 'var(--text-lg)',
              minHeight: 'var(--touch-min)',
              padding: 'var(--space-4) var(--space-5)',
              width: '100%',
            }}
            type="submit"
          >
            使用已連結的 LINE 登入
          </button>
        </form>
      )}
      {showLine && (
        <p
          style={{
            color: 'var(--color-foreground)',
            fontSize: 'var(--text-base)',
            lineHeight: 'var(--leading-body)',
            marginTop: 'var(--space-3)',
          }}
        >
          LINE 只能登入已在「登入方式」完成連結的帳號，不能建立或合併新帳號。
        </p>
      )}
      <p
        style={{
          color: 'var(--color-foreground)',
          fontSize: 'var(--text-base)',
          lineHeight: 'var(--leading-body)',
          marginTop: 'var(--space-6)',
        }}
      >
        需要協助嗎？請家人或照服員陪您一起完成設定。
      </p>
      <a href="/sign-in" style={touchLinkStyle}>
        返回選擇服務
      </a>
    </main>
  );
}
