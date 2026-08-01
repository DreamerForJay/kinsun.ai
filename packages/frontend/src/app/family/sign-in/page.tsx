'use client';

import { useLocale } from '@/lib/i18n/locale-context';

export default function FamilySignInPage() {
  const { t } = useLocale();

  return (
    <main style={{ margin: '80px auto', maxWidth: 520, padding: 24, textAlign: 'center' }}>
      <h1 style={{ fontSize: 28 }}>{t('familySignIn.title')}</h1>
      <p style={{ color: 'var(--color-foreground)', lineHeight: 1.7, margin: '20px 0' }}>
        {t('familySignIn.body')}
      </p>
      <form action="/backend/auth/login" method="post">
        <input name="intent" type="hidden" value="FAMILY" />
        <input name="returnTo" type="hidden" value="/onboarding/resolve" />
        <button type="submit">{t('common.continueWithGoogle')}</button>
      </form>
    </main>
  );
}
