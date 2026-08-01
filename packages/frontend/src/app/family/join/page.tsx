export default function FamilyJoinPage() {
  return (
    <main style={{ margin: '0 auto', maxWidth: 560, padding: 24 }}>
      <h1 style={{ fontSize: 28 }}>家屬服務</h1>
      <p style={{ color: '#4a5568', lineHeight: 1.7 }}>
        請輸入服務單位提供的邀請碼。系統會先用 Google 確認您的身分，再確認您可查看的報表範圍。
      </p>
      <p style={{ color: '#4a5568', lineHeight: 1.7 }}>
        邀請碼不會直接提供資料存取權；邀請核銷會在受保護的伺服器流程中完成。
      </p>
      <form action="/backend/auth/login" method="post" style={{ marginTop: 20 }}>
        <input name="intent" type="hidden" value="FAMILY" />
        <input name="returnTo" type="hidden" value="/onboarding/resolve" />
        <label
          htmlFor="invitationCode"
          style={{ display: 'block', fontWeight: 700, marginBottom: 8 }}
        >
          家屬邀請碼
        </label>
        <input
          autoComplete="one-time-code"
          id="invitationCode"
          name="invitationCode"
          required
          style={{ boxSizing: 'border-box', fontSize: 18, padding: 12, width: '100%' }}
        />
        <button
          style={{
            background: '#1d4ed8',
            border: 0,
            borderRadius: 10,
            color: 'white',
            fontSize: 18,
            marginTop: 14,
            padding: '14px 18px',
          }}
          type="submit"
        >
          使用 Google 繼續
        </button>
      </form>
      <p style={{ marginTop: 24 }}>
        已完成綁定？ <a href="/family/sign-in">前往家屬登入</a>
      </p>
      <a href="/sign-in">返回選擇服務</a>
    </main>
  );
}
