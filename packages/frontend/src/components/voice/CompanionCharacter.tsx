'use client';

import styles from './CompanionCharacter.module.css';

/** Presentation-only animation states. Mapped from `VoicePageState` at the call
 * site so this component stays independent of the page state machine. */
export type ConversationState = 'idle' | 'listening' | 'processing' | 'speaking' | 'sleeping';

interface CompanionCharacterProps {
  state: ConversationState;
  message?: string;
  characterName?: string;
}

export function CompanionCharacter({ state = 'idle', message, characterName = '小暖' }: CompanionCharacterProps) {
  return (
    <div className={styles.container}>
      <div className={`${styles.characterWrapper} ${styles[state]}`}>
        {/* Static glow behind the character — colour only, no timeline of its own (§9). */}
        <div className={styles.glow} />

        <div className={styles.character}>
          {/* Plain <img>, not next/image — this is a bundled local asset, and
              the optimizer's default sandbox CSP on /_next/image responses
              isn't worth the tradeoff for a fixed 280x280 static PNG. */}
          <img src="/mascot.png" alt={characterName} width={280} height={280} className={styles.characterImage} />
        </div>
      </div>

      {/* Speech bubble */}
      {message && state !== 'sleeping' && (
        <div className={styles.speechBubble}>
          <p className={styles.messageText}>{message}</p>
        </div>
      )}

      {/* Character name tag */}
      <div className={styles.nameTag}>{characterName}</div>
    </div>
  );
}
