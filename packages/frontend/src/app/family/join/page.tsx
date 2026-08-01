'use client';

import { useLocale } from '@/lib/i18n/locale-context';

export default function FamilyJoinPage() {
  const { t } = useLocale();

  return (
    <main style={{ margin: '0 auto', maxWidth: 560, padding: 24 }}>
      <h1 style={{ fontSize: 28 }}>{t('join.title')}</h1>
      <p style={{ color: '#4a5568', lineHeight: 1.7 }}>{t('join.intro')}</p>
      <p style={{ color: '#4a5568', lineHeight: 1.7 }}>{t('join.note')}</p>
      {/* Native form post to the BFF: redemption stays server-side, so this page
          needs no JavaScript to work beyond the language switch. */}
      <form action="/backend/auth/login" method="post" style={{ marginTop: 20 }}>
        <input name="intent" type="hidden" value="FAMILY" />
        <input name="returnTo" type="hidden" value="/onboarding/resolve" />
        <label
          htmlFor="invitationCode"
          style={{ display: 'block', fontWeight: 700, marginBottom: 8 }}
        >
          {t('join.codeLabel')}
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
          {t('common.continueWithGoogle')}
        </button>
      </form>
      <p style={{ marginTop: 24 }}>
        {t('join.alreadyBound')} <a href="/family/sign-in">{t('join.toFamilySignIn')}</a>
      </p>
      <a href="/sign-in">{t('join.backToChooser')}</a>
    </main>
  );
}
