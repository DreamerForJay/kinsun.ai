'use client';

import { useEffect, useState } from 'react';
import { CompanionTextPanel } from '@/components/companion/CompanionTextPanel';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { readDevPreviewState } from '@/components/voice/dev-preview';
import { VoiceInteractionPanel } from '@/components/voice/VoiceInteractionPanel';
import { activeBasicVoiceConsent, listConsents } from '@/lib/api/consent';
import {
  getRuntimeConfig,
  getVoiceSessionConfig,
  type RuntimeConfig,
  type VoiceSessionConfig,
} from '@/lib/runtime-config';

export default function HomePage() {
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const [voiceSession, setVoiceSession] = useState<VoiceSessionConfig | null>(null);
  const [isDevPreview, setIsDevPreview] = useState(false);
  const [consentGranted, setConsentGranted] = useState<boolean | null>(null);
  const [consentError, setConsentError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void getRuntimeConfig().then((nextConfig) => {
      if (!cancelled) setConfig(nextConfig);
    });
    setVoiceSession(getVoiceSessionConfig());
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
        <VoiceInteractionPanel wsUrl="" token="" consentGranted />
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
      {!consentError && consentGranted === true && voiceSession?.wsUrl && voiceSession.token && (
        <VoiceInteractionPanel
          wsUrl={voiceSession.wsUrl}
          token={voiceSession.token}
          consentGranted={consentGranted}
        />
      )}
      {!consentError && consentGranted === true && !(voiceSession?.wsUrl && voiceSession.token) && (
        <CompanionTextPanel apiConfig={config} elderId={config.elderId} />
      )}

      <nav style={{ display: 'flex', gap: 'var(--space-4)', fontSize: 'var(--text-sm)' }}>
        <a href="/consent">同意設定</a>
        <a href="/elder/family-access">家屬分享</a>
        <a href="/sign-in">登入</a>
      </nav>
    </main>
  );
}
