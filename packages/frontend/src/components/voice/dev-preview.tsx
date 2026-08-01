'use client';

import { ALL_VOICE_PAGE_STATES, isVoicePageState, STATE_COPY, type VoicePageState } from './voice-page-state';

/**
 * DEV SEAM — delete or replace this file when real Cognito sign-in lands.
 *
 * Several of the 9 states design-system/MASTER.md §10.1 requires cannot be
 * produced by the backend yet (Low Confidence has no server field, Generating is
 * not reported separately), and with no auth provider there is no way to reach
 * the voice page locally at all. `?previewState=<state>` forces one state so the
 * visuals can be reviewed.
 *
 * This is NOT a substitute for consent. The preview renders states only — it
 * constructs no recorder and no socket, so no audio is captured. Real recording
 * still requires the consent gate in VoiceInteractionPanel, which is untouched
 * for every non-preview render.
 *
 * `process.env.NODE_ENV` is inlined at build time, so everything below is dead
 * code in a production build.
 */

/** Reads `?previewState=<state>`. The NODE_ENV guard lives here and nowhere else. */
export function readDevPreviewState(): VoicePageState | null {
  if (process.env.NODE_ENV === 'production') return null;
  if (typeof window === 'undefined') return null;
  const raw = new URLSearchParams(window.location.search).get('previewState');
  return raw !== null && isVoicePageState(raw) ? raw : null;
}

/**
 * Honesty banner + state switch. Static by design: §9 allows exactly one
 * animated element on the voice surface and the mascot/record button owns it,
 * so nothing here transitions or animates. Stays in normal flow (no
 * `position: fixed`) so it cannot overlap the mascot or the record button.
 */
export function DevPreviewBanner({ active }: { active: VoicePageState }) {
  if (process.env.NODE_ENV === 'production') return null;

  return (
    <div
      style={{
        width: '100%',
        maxWidth: 640,
        /* It renders outside the voice <main>, i.e. in the block flow of
           <body>, so centring cannot come from a flex parent. */
        marginInline: 'auto',
        boxSizing: 'border-box',
        padding: 'var(--space-4)',
        borderRadius: 'var(--radius-md)',
        border: '2px dashed var(--color-border-strong)',
        background: 'var(--state-candidate-bg)',
        color: 'var(--state-candidate-fg)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-3)',
      }}
    >
      <p
        style={{
          margin: 0,
          fontSize: 'var(--text-sm)',
          lineHeight: 'var(--leading-body)',
          color: 'var(--state-candidate-fg)',
        }}
      >
        設計預覽（僅開發環境）：不會錄音、未連線後端，畫面僅供視覺檢視。這裡顯示的內容不是真實對話結果。
      </p>

      <nav
        aria-label="設計預覽狀態切換"
        style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)' }}
      >
        {ALL_VOICE_PAGE_STATES.map((state) => {
          const isActive = state === active;
          return (
            <a
              key={state}
              href={`/?previewState=${state}`}
              aria-current={isActive ? 'page' : undefined}
              title={STATE_COPY[state]}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                minHeight: 'var(--touch-min)',
                padding: '0 var(--space-4)',
                borderRadius: 'var(--radius-sm)',
                fontSize: 'var(--text-sm)',
                lineHeight: 'var(--leading-body)',
                /* Active is marked by weight + border + fill, not colour alone (§4.2). */
                fontWeight: isActive ? 700 : 400,
                border: isActive
                  ? '2px solid var(--color-primary)'
                  : '2px solid var(--color-border)',
                background: isActive ? 'var(--color-primary-weak)' : 'var(--color-surface)',
                color: isActive ? 'var(--color-primary-text)' : 'var(--color-muted-foreground)',
                textDecoration: 'none',
              }}
            >
              {isActive ? `● ${state}` : state}
            </a>
          );
        })}
      </nav>
    </div>
  );
}
