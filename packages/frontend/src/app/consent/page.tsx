'use client';

import { useRouter } from 'next/navigation';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { ConsentPanel } from '@/components/voice/ConsentPanel';
import { AUTH_STORAGE_KEYS, getRuntimeConfig } from '@/lib/runtime-config';

export default function ConsentPage() {
  const router = useRouter();
  const config = getRuntimeConfig();

  if (!config.token || !config.elderId) {
    return <NotLoggedIn reason="尚未設定登入資訊，請先完成登入設定" />;
  }

  return (
    <main style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <ConsentPanel
        apiConfig={{ apiBaseUrl: config.apiBaseUrl, token: config.token }}
        elderId={config.elderId}
        initialGranted={false}
        onChange={(granted) => {
          window.localStorage.setItem(AUTH_STORAGE_KEYS.consentGranted, String(granted));
          if (granted) router.push('/');
        }}
      />
    </main>
  );
}
