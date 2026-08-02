'use client';

import { HourglassMedium } from '@phosphor-icons/react';
import { useEffect, useState } from 'react';
import { CompanionTextPanel } from '@/components/companion/CompanionTextPanel';
import { InputModeToggle, type InputMode } from '@/components/InputModeToggle';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { SignOutButton } from '@/components/SignOutButton';
import { touchLinkStyle } from '@/components/touch-link';
import { activeBasicVoiceConsent, listConsents } from '@/lib/api/consent';
import { getRuntimeConfig, type RuntimeConfig } from '@/lib/runtime-config';
import { readDevPreviewState } from './dev-preview';
import { VoiceInteractionPanel } from './VoiceInteractionPanel';
import styles from './VoiceHomeClient.module.css';

/**
 * The elder voice companion screen. Moved out of `app/page.tsx` so the route
 * can fork server-side on session-cookie presence: signed-in visitors reach
 * this canonical voice flow; signed-out visitors get the public landing page
 * instead (see `app/page.tsx`). Core still re-authorizes every read regardless
 * of which branch rendered it.
 */
export function VoiceHomeClient() {
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const [configLoadFailed, setConfigLoadFailed] = useState(false);
  const [isDevPreview, setIsDevPreview] = useState(false);
  const [inputMode, setInputMode] = useState<InputMode>('voice');
  const [consentGranted, setConsentGranted] = useState<boolean | null>(null);
  const [consentError, setConsentError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void getRuntimeConfig()
      .then((nextConfig) => {
        if (!cancelled) setConfig(nextConfig);
      })
      .catch(() => {
        if (!cancelled) setConfigLoadFailed(true);
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
        <VoiceInteractionPanel apiConfig={{ apiBaseUrl: '' }} elderId="" consentGranted />
      </main>
    );
  }

  if (configLoadFailed || config?.credentialStatus === 'unavailable') {
    return <NotLoggedIn reason="無法確認登入憑證狀態；系統已停止，不會略過認證" />;
  }
  if (!config) {
    return (
      <main data-surface="voice" className={styles.loadingPage} aria-busy="true">
        <HourglassMedium
          size={48}
          weight="fill"
          aria-hidden="true"
          className={styles.loadingIcon}
        />
        <h1 className={styles.loadingTitle}>智慧長照 AI 陪伴系統</h1>
        <p role="status" aria-live="polite" className={styles.loadingMessage}>
          正在準備陪伴服務，請稍候…
        </p>
      </main>
    );
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

      {/* Everything below this point renders only when credentialStatus is
          'present', so the elder is signed in. The link here used to be an
          unconditional "登入", which told a signed-in elder to sign in again and
          left no way to sign out at all. */}
      <nav
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'center',
          gap: 'var(--space-4)',
        }}
      >
        <a href="/consent" style={touchLinkStyle}>
          同意設定
        </a>
        <a href="/elder/family-access" style={touchLinkStyle}>
          家屬分享
        </a>
        <SignOutButton label="登出" />
      </nav>
    </main>
  );
}
