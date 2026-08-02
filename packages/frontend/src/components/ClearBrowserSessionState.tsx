'use client';

import { useEffect } from 'react';
import { clearBrowserSessionState } from '@/lib/runtime-config';

/**
 * Backstop for sign-out, mounted on `/sign-in` only when the server sees no
 * access-token cookie.
 *
 * Clearing here covers paths SignOutButton's handler cannot: an expired
 * session, a form submitted before hydration, and direct navigation on a
 * shared device. The server page deliberately does not mount this component
 * while a cookie remains, because a failed re-auth must not erase the current
 * browser selection while leaving the HttpOnly session intact.
 *
 * Renders nothing.
 */
export function ClearBrowserSessionState() {
  useEffect(() => {
    clearBrowserSessionState();
  }, []);
  return null;
}
