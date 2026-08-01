'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ApiRequestError, apiFetch } from '@/lib/api/client';

interface ActorProfile {
  actor_type?: string;
  role?: string;
  elder_id?: string | null;
}

interface AuthorizedElderList {
  items: Array<{ elder_id: string }>;
}

const ELDER_STORAGE_KEY = 'elderly_care_elder_id';

function destinationFor(profile: ActorProfile): string | null {
  const role = profile.role ?? profile.actor_type;
  if (role === 'ELDER') return '/';
  if (role === 'FAMILY_MEMBER') return '/family';
  if (role === 'DAYCARE_CARE_WORKER' || role === 'HOME_CARE_WORKER') return '/dashboard';
  return null;
}

export default function ResolveOnboardingPage() {
  const router = useRouter();
  const [message, setMessage] = useState('正在確認您可使用的服務…');

  useEffect(() => {
    let cancelled = false;
    void apiFetch<ActorProfile>({ apiBaseUrl: '/backend/core' }, '/api/v1/me')
      .then(async (profile) => {
        if (cancelled) return;
        const role = profile.role ?? profile.actor_type;
        if (role === 'ELDER' && profile.elder_id) {
          window.localStorage.setItem(ELDER_STORAGE_KEY, profile.elder_id);
        } else if (role === 'FAMILY_MEMBER') {
          const elders = await apiFetch<AuthorizedElderList>(
            { apiBaseUrl: '/backend/core' },
            '/api/v1/me/authorized-elders?mode=family&limit=100',
          );
          if (cancelled) return;
          const firstElder = elders.items[0]?.elder_id;
          if (!firstElder) {
            setMessage('目前沒有可存取的長者，請確認邀請是否仍有效。');
            return;
          }
          window.localStorage.setItem(ELDER_STORAGE_KEY, firstElder);
        }
        const destination = destinationFor(profile);
        if (destination) router.replace(destination);
        else setMessage('這個帳號尚未完成服務啟用，請聯絡服務單位。');
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setMessage(
          error instanceof ApiRequestError && error.status === 401
            ? '登入狀態已失效，請再試一次。'
            : '目前無法確認帳號資格，請稍後再試或聯絡服務單位。',
        );
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  return (
    <main style={{ margin: '80px auto', maxWidth: 520, padding: 24, textAlign: 'center' }}>
      <p aria-live="polite">{message}</p>
      <p>
        <a href="/sign-in">返回登入入口</a>
      </p>
    </main>
  );
}
