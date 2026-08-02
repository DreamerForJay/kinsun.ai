export const dynamic = 'force-dynamic';

import { FamilySignInView } from './FamilySignInView';

/** See family/join/page.tsx for why this server/client split exists. */
export default function FamilySignInPage() {
  const showLine = process.env.LINE_LOGIN_ENABLED?.trim().toLowerCase() === 'true';
  return <FamilySignInView showLine={showLine} />;
}
