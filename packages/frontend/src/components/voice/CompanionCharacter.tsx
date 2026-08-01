'use client';

import { useEffect, useRef } from 'react';
import styles from './CompanionCharacter.module.css';

/** Presentation-only animation states. Mapped from `VoicePageState` at the call
 * site so this component stays independent of the page state machine. */
export type ConversationState = 'idle' | 'listening' | 'processing' | 'speaking' | 'sleeping';

interface CompanionCharacterProps {
  state: ConversationState;
  message?: string;
  characterName?: string;
}

/**
 * Per-state video clips — a state without an entry keeps the static
 * mascot.png. This is a drop-in replacement for §9's "one animated element"
 * on the voice surface, not an addition to it, so only ever one of
 * video/img is mounted at a time.
 */
const STATE_VIDEO: Partial<Record<ConversationState, string>> = {
  idle: '/video/happy.mp4',
  listening: '/video/listen.mp4',
  processing: '/video/remind.mp4',
  speaking: '/video/encourage.mp4',
  sleeping: '/video/comfort.mp4',
};

export function CompanionCharacter({ state = 'idle', message, characterName = '小暖' }: CompanionCharacterProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const videoSrc = STATE_VIDEO[state];

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    // §13 motion off, no information lost — same principle as the CSS
    // breathe animation below: reduced-motion users get the clip's first
    // frame, not a looping video.
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      video.pause();
      return;
    }
    video.play().catch(() => {
      /* Autoplay can be blocked until a user gesture fires — the record-
         button press that triggers `listening` always counts as one, so
         this only matters for states reached without a prior tap. */
    });
  }, [videoSrc]);

  return (
    <div className={styles.container}>
      <div className={`${styles.characterWrapper} ${styles[state]}`}>
        {/* Static glow behind the character — colour only, no timeline of its own (§9). */}
        <div className={styles.glow} />

        <div className={styles.character}>
          {videoSrc ? (
            <video
              ref={videoRef}
              key={videoSrc}
              src={videoSrc}
              loop
              muted
              playsInline
              preload="auto"
              width={280}
              height={280}
              className={styles.characterImage}
              aria-label={characterName}
            />
          ) : (
            // Plain <img>, not next/image — this is a bundled local asset, and
            // the optimizer's default sandbox CSP on /_next/image responses
            // isn't worth the tradeoff for a fixed 280x280 static PNG.
            <img src="/mascot.png" alt={characterName} width={280} height={280} className={styles.characterImage} />
          )}
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
