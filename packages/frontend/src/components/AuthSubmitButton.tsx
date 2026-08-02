'use client';

import type { ReactNode } from 'react';

/**
 * The "continue with Google" submit button, shared by every sign-in entry point.
 *
 * It exists because two of the three copies were a bare <button> with no styles
 * at all, rendering 23px tall — half of MASTER.md §6.1's 48px floor, on the
 * screens where a family member or care worker first arrives. A fourth
 * hand-rolled copy would have drifted the same way.
 *
 * The fill is --color-primary-strong rather than --color-primary: the label sits
 * below 24px, so it needs the 4.5:1 body-text ratio, and white on
 * --color-primary is only 3.68:1 (§4.1, §13).
 */
export function AuthSubmitButton({ children }: { children: ReactNode }) {
  return (
    <button
      type="submit"
      style={{
        background: 'var(--color-primary-strong)',
        border: 0,
        borderRadius: 'var(--radius-md)',
        color: 'var(--color-on-primary)',
        cursor: 'pointer',
        fontFamily: 'inherit',
        fontSize: 'var(--text-base)',
        // Height comes from min-height so a 200% system font size grows the
        // control instead of clipping the label (§5.1).
        minHeight: 'var(--touch-min)',
        padding: 'var(--space-3) var(--space-6)',
      }}
    >
      {children}
    </button>
  );
}
