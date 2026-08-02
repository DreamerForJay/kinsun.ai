export const dynamic = 'force-dynamic';

import { StaffSignInView } from './StaffSignInView';

/** See family/join/page.tsx for why this server/client split exists. */
export default function StaffSignInPage() {
  const showLine = process.env.LINE_LOGIN_ENABLED?.trim().toLowerCase() === 'true';
  return <StaffSignInView showLine={showLine} />;
}
