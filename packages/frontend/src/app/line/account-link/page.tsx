import { cookies } from 'next/headers';
import { LineAccountLinkClient } from '@/components/LineAccountLinkClient';
import {
  lineLinkCookieName,
  normalizeLineLinkToken,
} from '@/lib/server/line-account-link';

export const dynamic = 'force-dynamic';

const ERRORS = new Set(['invalid_link', 'link_expired', 'link_failed', 'service_unavailable']);

export default async function LineAccountLinkPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; status?: string }>;
}) {
  const [{ error, status }, cookieStore] = await Promise.all([searchParams, cookies()]);
  const hasPendingLinkToken =
    normalizeLineLinkToken(cookieStore.get(lineLinkCookieName())?.value) !== null;
  const initialError = ERRORS.has(error ?? '')
    ? (error as 'invalid_link' | 'link_expired' | 'link_failed' | 'service_unavailable')
    : undefined;
  const initialNotice = status === 'already_linked' ? 'already_linked' : undefined;
  return (
    <LineAccountLinkClient
      hasPendingLinkToken={hasPendingLinkToken}
      initialError={initialError}
      initialNotice={initialNotice}
    />
  );
}
