interface NotLoggedInProps {
  reason: string;
}

/**
 * Shown instead of a bare error string whenever a page has no usable
 * token/elderId, or the API rejects them with 403 — both cases point
 * somewhere actionable (there is no Cognito Hosted UI yet, see
 * lib/runtime-config.ts) rather than leaving the user stuck on "讀取失敗".
 */
export function NotLoggedIn({ reason }: NotLoggedInProps) {
  return (
    <main style={{ maxWidth: 480, margin: '80px auto', padding: 24, textAlign: 'center' }}>
      <p style={{ color: '#718096', marginBottom: 16 }}>{reason}</p>
      <a href="/dev-login" style={{ color: '#2b6cb0' }}>
        前往登入設定 →
      </a>
    </main>
  );
}
