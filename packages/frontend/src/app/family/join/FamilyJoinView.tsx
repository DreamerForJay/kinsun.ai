'use client';

import { touchLinkStyle } from '@/components/touch-link';
import { useLocale } from '@/lib/i18n/locale-context';

export function FamilyJoinView({ showLine }: { showLine: boolean }) {
  const { t } = useLocale();

  return (
    <main style={{ margin: '0 auto', maxWidth: 560, padding: 24 }}>
      <h1 style={{ fontSize: 28 }}>{t('join.title')}</h1>
      <p style={{ color: 'var(--color-foreground)', lineHeight: 1.7 }}>{t('join.intro')}</p>
      <p style={{ color: 'var(--color-foreground)', lineHeight: 1.7 }}>{t('join.note')}</p>
      {/* Native form post to the BFF: redemption stays server-side, so this page
          needs no JavaScript to work beyond the language switch. */}
      <form action="/backend/auth/login" method="post" style={{ marginTop: 20 }}>
        <input name="intent" type="hidden" value="FAMILY" />
        <input name="provider" type="hidden" value="GOOGLE" />
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
            /* --color-primary-strong, not --color-primary: this label is 18px,
               so it needs 4.5:1 rather than the 3:1 large-text bar (§13). */
            background: 'var(--color-primary-strong)',
            border: 0,
            borderRadius: 'var(--radius-md)',
            color: 'var(--color-on-primary)',
            fontSize: 'var(--text-base)',
            marginTop: 'var(--space-4)',
            minHeight: 'var(--touch-min)',
            padding: 'var(--space-3) var(--space-5)',
          }}
          type="submit"
        >
          {t('common.continueWithGoogle')}
        </button>
      </form>
      {showLine && (
        <form action="/backend/auth/login" method="post" style={{ marginTop: 'var(--space-5)' }}>
          <input name="intent" type="hidden" value="FAMILY" />
          <input name="provider" type="hidden" value="LINE" />
          <input name="returnTo" type="hidden" value="/onboarding/resolve" />
          <button
            style={{
              background: 'var(--color-surface)',
              border: '1px solid var(--color-border-strong)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--color-primary-text)',
              fontSize: 'var(--text-base)',
              minHeight: 'var(--touch-min)',
              padding: 'var(--space-3) var(--space-5)',
            }}
            type="submit"
          >
            {t('join.lineButton')}
          </button>
          <p style={{ color: 'var(--color-foreground)', lineHeight: 1.6, marginTop: 'var(--space-2)' }}>
            {t('join.lineHint')}
          </p>
        </form>
      )}
      <p style={{ marginTop: 'var(--space-6)' }}>
        {t('join.alreadyBound')}{' '}
        <a href="/family/sign-in" style={touchLinkStyle}>
          {t('join.toFamilySignIn')}
        </a>
      </p>
      <a href="/sign-in" style={touchLinkStyle}>
        {t('join.backToChooser')}
      </a>
    </main>
  );
}
