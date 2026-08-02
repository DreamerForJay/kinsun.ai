export const dynamic = 'force-dynamic';

import { FamilyJoinView } from './FamilyJoinView';

/**
 * Server wrapper: LINE_LOGIN_ENABLED is a server-only flag (not NEXT_PUBLIC_,
 * so a client component can't read it directly), decided per-request the same
 * way the actual /backend/auth/login route gates LINE sign-in. The i18n hook
 * needs a client component, so the real markup lives in FamilyJoinView.
 */
export default function FamilyJoinPage() {
  const showLine = process.env.LINE_LOGIN_ENABLED?.trim().toLowerCase() === 'true';
  return <FamilyJoinView showLine={showLine} />;
}
