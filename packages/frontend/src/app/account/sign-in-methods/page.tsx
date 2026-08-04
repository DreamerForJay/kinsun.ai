import { SignInMethodsClient } from '@/components/SignInMethodsClient';

const notices: Record<string, string> = {
  linked: 'LINE Login 已成功連結；之後可用 Google 或 LINE 登入同一個帳號。',
  already_linked: '這個帳號已經連結 LINE Login。',
};

const errors: Record<string, string> = {
  google_required: '必須先用已連結的 Google 帳號登入，才能新增 LINE Login。',
  line_email_mismatch:
    'LINE 帳號的 Email 與目前已驗證的 Cognito Email 不一致，因此沒有連結，也不會自動合併帳號。',
  line_identity_conflict: '這個 LINE Login 已屬於其他 Cognito 使用者，系統不會轉移或合併帳號。',
  link_destination_changed: '連結期間登入帳號已變更，因此系統已取消操作，請重新開始。',
  line_link_failed: 'LINE Login 連結沒有完成，請再試一次。',
  session_expired: '登入狀態已失效；請重新以 Google 登入後再新增 LINE Login。',
};

export const dynamic = 'force-dynamic';

export default async function SignInMethodsPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; status?: string }>;
}) {
  const params = await searchParams;
  const notice = params.status ? notices[params.status] : undefined;
  const error = params.error ? errors[params.error] : undefined;

  return (
    <main style={{ margin: '0 auto', maxWidth: 620, padding: 24 }}>
      <h1 style={{ fontSize: 28 }}>登入方式</h1>
      <p style={{ color: 'var(--color-muted-foreground)', lineHeight: 1.7 }}>
        Google 與 LINE Login 會連到同一個 Cognito 使用者；Core 仍只以 Cognito sub 對應正式
        Actor，不會依 Email 自動合併 Actor。
      </p>
      {notice && (
        <p role="status" style={{ color: 'var(--state-confirmed-fg)' }}>
          {notice}
        </p>
      )}
      {error && (
        <p role="alert" style={{ color: 'var(--color-destructive)' }}>
          {error}
        </p>
      )}
      <SignInMethodsClient />
      <p style={{ color: 'var(--color-muted-foreground)', lineHeight: 1.7, marginTop: 24 }}>
        LINE Bot 的官方 Account Linking 是另一套 Messaging API 身分，不會在此顯示，也不會與 LINE
        Login subject 混用。
      </p>
      <a href="/">返回服務首頁</a>
    </main>
  );
}
