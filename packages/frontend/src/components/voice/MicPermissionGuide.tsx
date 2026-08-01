'use client';

import { MicrophoneSlash } from '@phosphor-icons/react';

export interface MicPermissionGuideProps {
  onRetry: () => void;
}

/**
 * Plain-language mic-permission guidance (A01.3, design-system/MASTER.md §10.1
 * Permission Denied — 附白話步驟). Tokens only, no raw hex (§14). The retry
 * button here is deliberately `secondary` (outline): the record button is
 * already the one filled button on this screen (§8.1).
 */
export function MicPermissionGuide({ onRetry }: MicPermissionGuideProps) {
  return (
    <div
      role="alert"
      style={{
        maxWidth: '36ch',
        margin: '0 auto',
        padding: 'var(--card-pad)',
        borderRadius: 'var(--radius-lg)',
        background: 'var(--color-surface)',
        border: '2px solid var(--color-border-strong)',
        boxShadow: 'var(--shadow-1)',
        textAlign: 'center',
        fontSize: 'var(--text-base)',
        lineHeight: 'var(--leading-body)',
        color: 'var(--color-foreground)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-4)',
        alignItems: 'center',
      }}
    >
      <MicrophoneSlash size={40} weight="fill" aria-hidden="true" color="var(--color-primary)" />
      <p style={{ margin: 0 }}>要先讓我使用麥克風才能說話。</p>
      <p style={{ margin: 0 }}>請在畫面上方的提示，點一下「允許」。</p>
      <button
        type="button"
        onClick={onRetry}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 'var(--space-3)',
          minHeight: 'var(--touch-rec)',
          padding: 'var(--space-3) var(--space-6)',
          fontSize: 'var(--text-base)',
          fontWeight: 700,
          borderRadius: 'var(--radius-md)',
          border: '2px solid var(--color-primary)',
          background: 'transparent',
          color: 'var(--color-primary-text)',
          cursor: 'pointer',
        }}
      >
        <MicrophoneSlash size={32} weight="fill" aria-hidden="true" />
        <span>再允許一次</span>
      </button>
    </div>
  );
}
