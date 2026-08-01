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
export function LanguageSwitch() {
  const { locale, setLocale, t } = useLocale();

  return (
    <div className={styles.group}>
      <span className={styles.label} id="language-switch-label">
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
              {/* Selected state is conveyed by text as well as colour (§4.2). */}
              {selected && (
                <span aria-hidden="true" className={styles.check}>
                  ✓
                </span>
              )}
              {t(option === 'en' ? 'lang.en' : 'lang.zh-Hant')}
            </button>
          );
        })}
      </div>
    </div>
  );
}
