'use client';

import type { SpeechLanguage } from '@/lib/voice/speech-gateway-client';

export interface LanguageOption {
  language: SpeechLanguage;
  label: string;
  /** Stated plainly when the reply cannot be spoken back in this language. */
  replyIsTextOnly: boolean;
}

export const LANGUAGE_OPTIONS: readonly LanguageOption[] = [
  { language: 'zh-TW', label: '國語', replyIsTextOnly: false },
  { language: 'nan-TW', label: '台語', replyIsTextOnly: true },
  { language: 'hak-TW', label: '客語', replyIsTextOnly: true },
  { language: 'en-US', label: 'English', replyIsTextOnly: false },
];

export interface LanguageSelectProps {
  language: SpeechLanguage;
  onChange: (language: SpeechLanguage) => void;
  /** Disabled mid-turn so the language cannot change under an in-flight utterance. */
  disabled?: boolean;
}

/**
 * Spoken-language selector.
 *
 * The language is chosen rather than detected because getting it wrong is not a
 * neutral error: transcribing Taiwanese with a Mandarin model returns fluent text
 * the elder never said, and that text would then be treated as what they said.
 *
 * Where the reply cannot be spoken back, the option says so up front instead of
 * letting the elder discover the silence after speaking.
 */
export function LanguageSelect({ language, onChange, disabled }: LanguageSelectProps) {
  const selected = LANGUAGE_OPTIONS.find((option) => option.language === language);

  return (
    <div style={{ width: '100%', maxWidth: '24rem' }}>
      <div
        role="radiogroup"
        aria-label="選擇您要說的語言"
        style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)' }}
      >
        {LANGUAGE_OPTIONS.map((option) => {
          const isSelected = option.language === language;
          return (
            <button
              key={option.language}
              type="button"
              role="radio"
              aria-checked={isSelected}
              disabled={disabled}
              onClick={() => onChange(option.language)}
              style={{
                flex: '1 1 auto',
                // Comfortably above the 44px minimum touch target.
                minHeight: '3rem',
                minWidth: '5rem',
                padding: 'var(--space-2) var(--space-3)',
                fontSize: 'var(--text-base)',
                fontFamily: 'inherit',
                borderRadius: 'var(--radius-lg, 0.75rem)',
                cursor: disabled ? 'not-allowed' : 'pointer',
                opacity: disabled ? 0.5 : 1,
                // Fill and border together, so selection survives greyscale.
                border: isSelected
                  ? '2px solid var(--color-primary)'
                  : '2px solid var(--color-border)',
                background: isSelected ? 'var(--color-primary)' : 'transparent',
                color: isSelected
                  ? 'var(--color-on-primary)'
                  : 'var(--color-foreground)',
                fontWeight: isSelected ? 600 : 400,
              }}
            >
              {option.label}
            </button>
          );
        })}
      </div>

      {selected?.replyIsTextOnly === true && (
        <p
          style={{
            margin: 'var(--space-2) 0 0',
            fontSize: 'var(--text-sm)',
            lineHeight: 'var(--leading-body)',
            color: 'var(--color-muted-foreground)',
          }}
        >
          {selected.label}目前可以聽懂您說的話，回答會用文字顯示，還沒辦法唸出來。
        </p>
      )}
    </div>
  );
}
