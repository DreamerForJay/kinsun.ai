'use client';

import { clearBrowserSessionState } from '@/lib/runtime-config';
import { touchLinkStyle } from './touch-link';

/**
 * Sign-out, wired to the BFF's `POST /backend/auth/logout`.
 *
 * A form rather than a link, for two reasons that are not stylistic: the route
 * only accepts POST and rejects untrusted origins (CSRF), and sign-out is a
 * state change, so it must not sit behind something a prefetcher or a crawler
 * can follow.
 *
 * The submit handler clears browser-side session state first, because the route
 * runs on the server and can only expire the HttpOnly cookies. It is not the
 * only place that happens: `/sign-in` clears it again after the server confirms
 * that no access-token cookie remains, so the form still works before hydration.
 *
 * `label` is passed in rather than read from the i18n context: the elder surface
 * has no LocaleProvider by design (MASTER.md §5.2), and `useLocale` throws
 * outside one.
 *
 * Deliberately secondary, never a filled primary button — §1 allows one filled
 * primary action per screen, and on the voice surface that is the record button.
 */
export function SignOutButton({ label }: { label: string }) {
  return (
    <form
      action="/backend/auth/logout"
      method="post"
      onSubmit={() => clearBrowserSessionState()}
      style={{ display: 'inline' }}
    >
      <button
        type="submit"
        style={{
          ...touchLinkStyle,
          background: 'none',
          border: 0,
          cursor: 'pointer',
          fontFamily: 'inherit',
          textDecoration: 'underline',
        }}
      >
        {label}
      </button>
    </form>
  );
}
