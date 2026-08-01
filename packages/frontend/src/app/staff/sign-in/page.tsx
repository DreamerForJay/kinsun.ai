'use client';

import { AuthSubmitButton } from '@/components/AuthSubmitButton';
import { useLocale } from '@/lib/i18n/locale-context';

export default function StaffSignInPage() {
  const { t } = useLocale();

  return (
    <main style={{ margin: '80px auto', maxWidth: 520, padding: 24, textAlign: 'center' }}>
      <h1 style={{ fontSize: 28 }}>{t('staffSignIn.title')}</h1>
      <p style={{ color: 'var(--color-foreground)', lineHeight: 1.7, margin: '20px 0' }}>
        {t('staffSignIn.body')}
      </p>
      <form action="/backend/auth/login" method="post">
        <input name="intent" type="hidden" value="STAFF" />
        <input name="returnTo" type="hidden" value="/onboarding/resolve" />
        <AuthSubmitButton>{t('common.continueWithGoogle')}</AuthSubmitButton>
      </form>
      <p style={{ color: 'var(--color-foreground)', marginTop: 24 }}>
        {t('staffSignIn.notActivated')}
      </p>
    </main>
  );
}
