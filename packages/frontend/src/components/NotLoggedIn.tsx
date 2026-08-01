interface NotLoggedInProps {
  reason: string;
  /** Care/family callers pass a translated label; the Chinese-only voice
   *  surface omits it and gets the default (MASTER.md §5.2). */
  linkLabel?: string;
}

/**
 * Shown instead of a bare error string whenever a page has no usable
 * credential/elderId, or the API rejects them with 403 — both cases point
 * somewhere actionable rather than leaving the user stuck on "讀取失敗".
 */
export function NotLoggedIn({ reason, linkLabel }: NotLoggedInProps) {
  return (
    /* Sized from tokens, so this inherits whichever surface it is rendered in:
       the elder scale by default (app/layout.tsx), the care or family scale
       inside SurfaceShell. The elder path reaches this component too, so a
       fixed 16px here would have broken §5.1 on the surface that needs it most. */
    <main
      style={{
        maxWidth: 520,
        margin: '80px auto',
        padding: 'var(--space-6)',
        textAlign: 'center',
      }}
    >
      <p
        style={{
          color: 'var(--color-muted-foreground)',
          fontSize: 'var(--text-base)',
          lineHeight: 'var(--leading-body)',
          marginBottom: 'var(--space-4)',
        }}
      >
        {reason}
      </p>
      <a
        href="/sign-in"
        style={{
          alignItems: 'center',
          color: 'var(--color-primary-text)',
          display: 'inline-flex',
          fontSize: 'var(--text-base)',
          justifyContent: 'center',
          minHeight: 'var(--touch-min)',
          padding: '0 var(--space-4)',
        }}
      >
        {linkLabel ?? '前往登入 →'}
      </a>
    </main>
  );
}
