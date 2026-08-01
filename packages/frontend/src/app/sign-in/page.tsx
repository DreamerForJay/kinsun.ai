import Link from 'next/link';

const cardStyle = {
  border: '1px solid var(--color-border-strong)',
  borderRadius: 'var(--radius-md)',
  color: 'inherit',
  display: 'block',
  padding: 20,
  textDecoration: 'none',
};

export default function SignInPage({ searchParams }: { searchParams: { error?: string } }) {
  return (
    <main style={{ margin: '0 auto', maxWidth: 620, padding: 24 }}>
      <h1 style={{ fontSize: 28, marginBottom: 8 }}>登入智慧長照 AI 陪伴系統</h1>
      <p style={{ color: 'var(--color-foreground)', lineHeight: 1.6, marginBottom: 24 }}>
        請選擇您要使用的服務。我們會先使用 Google 確認身分，再由系統確認可使用的資料範圍。
      </p>
      {searchParams.error && (
        <p role="alert" style={{ color: 'var(--color-destructive)', marginBottom: 16 }}>
          這次登入沒有完成，請再試一次；若持續失敗，請聯絡服務單位。
        </p>
      )}
      <div style={{ display: 'grid', gap: 14 }}>
        <Link href="/elder/start" style={cardStyle}>
          <strong style={{ fontSize: 20 }}>我是長者</strong>
          <p style={{ marginBottom: 0 }}>用簡單的大按鈕開始語音陪伴。</p>
        </Link>
        <Link href="/family/join" style={cardStyle}>
          <strong style={{ fontSize: 20 }}>我是家屬</strong>
          <p style={{ marginBottom: 0 }}>使用邀請連結或登入後查看已授權的報表。</p>
        </Link>
        <Link href="/staff/sign-in" style={cardStyle}>
          <strong style={{ fontSize: 20 }}>我是照服員／居服員</strong>
          <p style={{ marginBottom: 0 }}>由所屬機構啟用的專業照護帳號登入。</p>
        </Link>
      </div>
    </main>
  );
}
