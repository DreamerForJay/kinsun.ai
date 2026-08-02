'use client';

import { useEffect, useState } from 'react';
import { CompanionTextPanel } from '@/components/companion/CompanionTextPanel';
import { InputModeToggle, type InputMode } from '@/components/InputModeToggle';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { readDevPreviewState } from '@/components/voice/dev-preview';
import { VoiceInteractionPanel } from '@/components/voice/VoiceInteractionPanel';
import { activeBasicVoiceConsent, listConsents } from '@/lib/api/consent';
import { getRuntimeConfig, type RuntimeConfig } from '@/lib/runtime-config';

export default function HomePage() {
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const [isDevPreview, setIsDevPreview] = useState(false);
  // Voice is the default: this is a voice-first product, and reaching for a
  // keyboard is the higher-effort path for the elders it serves.
  const [inputMode, setInputMode] = useState<InputMode>('voice');
  const [consentGranted, setConsentGranted] = useState<boolean | null>(null);
  const [consentError, setConsentError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void getRuntimeConfig().then((nextConfig) => {
      if (!cancelled) setConfig(nextConfig);
    });
    // The preview needs no credentials — it renders CompanionCharacter's
    // states only, opens no socket (see VoiceInteractionPanel's isPreview
    // gate), so it must not be blocked behind a real voice session existing.
    setIsDevPreview(readDevPreviewState() !== null);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (config?.credentialStatus !== 'present' || !config.elderId) return;
    let cancelled = false;
    listConsents(config, config.elderId)
      .then((items) => {
        if (!cancelled) setConsentGranted(activeBasicVoiceConsent(items) !== null);
      })
      .catch(() => {
        if (!cancelled) setConsentError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [config]);

  // The preview needs no credentials and no consent — it renders
  // CompanionCharacter's states only and opens no socket (see
  // VoiceInteractionPanel's isPreview gate), so none of the real-session
  // gates below should block it.
  if (isDevPreview) {
    return (
      <main
        data-surface="voice"
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          minHeight: '100dvh',
          gap: 'var(--block-gap)',
          padding: 'var(--space-6)',
          paddingBottom: 'calc(var(--space-6) + env(safe-area-inset-bottom))',
          background: 'var(--color-background)',
        }}
      >
        <h1 style={{ fontSize: 'var(--text-xl)', color: 'var(--color-foreground)', margin: 0 }}>
          智慧長照 AI 陪伴系統
        </h1>
        <VoiceInteractionPanel
          apiConfig={{ apiBaseUrl: '' }}
          elderId=""
          consentGranted
        />
      </main>
    );
  }

  if (!config) return null;
  if (config.credentialStatus === 'unavailable') {
    return <NotLoggedIn reason="無法確認登入憑證狀態；系統已停止，不會略過認證" />;
  }
  if (config.credentialStatus !== 'present' || !config.elderId) {
    return <NotLoggedIn reason="尚未設定本機 Demo 身分，請先完成登入設定" />;
  }

  return (
    <main
      data-surface="voice"
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        minHeight: '100dvh',
        gap: 'var(--block-gap)',
        padding: 'var(--space-6)',
        paddingBottom: 'calc(var(--space-6) + env(safe-area-inset-bottom))',
        background: 'var(--color-background)',
      }}
    >
      <h1 style={{ fontSize: 'var(--text-xl)', color: 'var(--color-foreground)', margin: 0 }}>
        智慧長照 AI 陪伴系統
      </h1>

      {consentError && (
        <p style={{ color: 'var(--color-destructive)' }}>
          無法向 Core API 確認同意狀態，系統不會開始陪伴。
        </p>
      )}
      {!consentError && consentGranted === null && <p>正在向 Core API 確認同意狀態…</p>}
      {!consentError && consentGranted === false && (
        <p>
          尚未取得 BASIC_VOICE 同意。<a href="/consent">前往同意設定</a>
        </p>
      )}
      {/* Both surfaces run the same canonical path over the same-origin BFF —
          recognition and synthesis via the speech gateway, reply from Core — so
          the choice here is only how the elder prefers to enter a turn.
          Rendering one at a time keeps the screen short and unambiguous. */}
      {!consentError && consentGranted === true && (
        <>
          <InputModeToggle mode={inputMode} onChange={setInputMode} />
          {inputMode === 'voice' ? (
            <VoiceInteractionPanel
              apiConfig={config}
              elderId={config.elderId}
              consentGranted={consentGranted}
            />
          ) : (
            <CompanionTextPanel apiConfig={config} elderId={config.elderId} />
          )}
        </>
      )}

      <nav style={{ display: 'flex', gap: 'var(--space-4)', fontSize: 'var(--text-sm)' }}>
        <a href="/consent">同意設定</a>
        <a href="/elder/family-access">家屬分享</a>
        <a href="/account/sign-in-methods">登入方式</a>
        <a href="/sign-in">登入</a>
      </nav>
    </main>
  );
}
