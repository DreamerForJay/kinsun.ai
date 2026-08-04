'use client';

import { useLocale } from '@/lib/i18n/locale-context';
import { LOCALES, type Locale } from '@/lib/i18n/messages';
import styles from './LanguageSwitch.module.css';

/**
 * UI language toggle for the care and family surfaces.
 *
 * Not rendered on the voice surface by design (MASTER.md §5.2) — and switching
 * here changes display language only. It never touches the elder's spoken
 * language preference or any other domain state.
 */
export function LanguageSwitch({ compactLabel = false }: { compactLabel?: boolean }) {
  const { locale, setLocale, t } = useLocale();

  return (
    <div className={styles.group}>
      <span
        className={styles.label}
        id="language-switch-label"
        data-visually-hidden={compactLabel}
      >
        {t('lang.label')}
      </span>
      <div className={styles.options} role="group" aria-labelledby="language-switch-label">
        {LOCALES.map((option: Locale) => {
          const selected = option === locale;
          return (
            <button
              key={option}
              type="button"
              className={styles.option}
              aria-pressed={selected}
              onClick={() => setLocale(option)}
            >
              {/* Keep the check slot in both options so changing locale never
                  changes the control's measured width. Visibility, text and
                  aria-pressed still convey the selected state (§4.2). */}
              <span aria-hidden="true" className={styles.check} data-visible={selected}>
                ✓
              </span>
              {t(option === 'en' ? 'lang.en' : 'lang.zh-Hant')}
            </button>
          );
        })}
      </div>
    </div>
  );
}
