export default function StaffSignInPage() {
  return (
    <main style={{ margin: '80px auto', maxWidth: 520, padding: 24, textAlign: 'center' }}>
      <h1 style={{ fontSize: 28 }}>照服員／居服員登入</h1>
      <p style={{ color: '#4a5568', lineHeight: 1.7, margin: '20px 0' }}>
        此帳號需要由所屬機構啟用。登入後，系統會依目前有效的機構歸屬與派案範圍顯示資料。
      </p>
      <form action="/backend/auth/login" method="post">
        <input name="intent" type="hidden" value="STAFF" />
        <input name="returnTo" type="hidden" value="/onboarding/resolve" />
        <button type="submit">使用 Google 繼續</button>
      </form>
      <p style={{ color: '#4a5568', marginTop: 24 }}>尚未啟用帳號？請聯絡所屬服務單位。</p>
    </main>
  );
}
