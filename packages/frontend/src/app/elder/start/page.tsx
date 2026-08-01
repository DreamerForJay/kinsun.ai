export default function ElderStartPage() {
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
      {/* A bare inline link is a small target; §6.1 forbids requiring precise
          taps on the elder surface, so it gets the same 64px box. */}
      <a
        href="/sign-in"
        style={{
          alignItems: 'center',
          display: 'inline-flex',
          fontSize: 'var(--text-base)',
          justifyContent: 'center',
          minHeight: 'var(--touch-min)',
          padding: '0 var(--space-4)',
        }}
      >
        返回選擇服務
      </a>
    </main>
  );
}
