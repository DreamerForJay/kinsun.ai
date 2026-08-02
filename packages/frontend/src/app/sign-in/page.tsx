import Link from 'next/link';

/* The role chooser is the one page whose audience is unknown — an elder, a
   family member and a care worker all land here before anything is known about
   them. It therefore renders at the elder scale (inherited from <body>): too
   large for a care worker costs nothing, too small for a 75+ user costs them
   the page (MASTER.md §5.1). Each card is a full 64px-plus target per §6.1. */
const cardStyle = {
  /* The border is this card's only affordance boundary, so WCAG 1.4.11 / §13's
     3:1 for UI components applies to it. --color-border-strong is 1.45:1 on
     white, which is decoration, not a boundary — --color-primary is 3.68:1. */
  border: '2px solid var(--color-primary)',
  borderRadius: 'var(--radius-md)',
  color: 'inherit',
  display: 'block',
  minHeight: 'var(--touch-min)',
  padding: 'var(--space-5)',
  textDecoration: 'none',
};

export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string | string[] }>;
}) {
  const { error } = await searchParams;
  return (
    <main style={{ margin: '0 auto', maxWidth: 680, padding: 'var(--space-6)' }}>
      <h1 style={{ fontSize: 'var(--text-2xl)', marginBottom: 'var(--space-2)' }}>
        登入智慧長照 AI 陪伴系統
      </h1>
      <p
        style={{
          color: 'var(--color-foreground)',
          fontSize: 'var(--text-base)',
          lineHeight: 'var(--leading-body)',
          marginBottom: 'var(--space-6)',
        }}
      >
        請選擇您要使用的服務。我們會先使用 Google 確認身分，再由系統確認可使用的資料範圍。
      </p>
      {error && (
        <p
          role="alert"
          style={{ color: 'var(--color-destructive)', marginBottom: 'var(--space-4)' }}
        >
          這次登入沒有完成，請再試一次；若持續失敗，請聯絡服務單位。
        </p>
      )}
      <div style={{ display: 'grid', gap: 'var(--space-4)' }}>
        <Link href="/elder/start" style={cardStyle}>
          <strong style={{ fontSize: 'var(--text-lg)' }}>我是長者</strong>
          <p style={{ marginBottom: 0 }}>用簡單的大按鈕開始語音陪伴。</p>
        </Link>
        <Link href="/family/join" style={cardStyle}>
          <strong style={{ fontSize: 'var(--text-lg)' }}>我是家屬</strong>
          <p style={{ marginBottom: 0 }}>使用邀請連結或登入後查看已授權的報表。</p>
        </Link>
        <Link href="/staff/sign-in" style={cardStyle}>
          <strong style={{ fontSize: 'var(--text-lg)' }}>我是照服員／居服員</strong>
          <p style={{ marginBottom: 0 }}>由所屬機構啟用的專業照護帳號登入。</p>
        </Link>
      </div>
    </main>
  );
}
