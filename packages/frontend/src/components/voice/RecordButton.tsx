'use client';

import {
  ArrowClockwise,
  Microphone,
  MicrophoneSlash,
  SpeakerHigh,
  SpinnerGap,
  Stop,
  WifiSlash,
  type Icon,
} from '@phosphor-icons/react';
import type { VoicePageState } from './voice-page-state';
import styles from './RecordButton.module.css';

/** Ring treatment per §10.1: breathing while listening, paused/inert otherwise. */
type Ring = 'none' | 'breathing' | 'paused';

interface StateAppearance {
  icon: Icon;
  /** Icon + text, never icon-only on the voice surface (§8.1). */
  label: string;
  /** Only two fills exist here — no red/amber/green health language (§2). */
  fill: 'primary' | 'accent';
  ring: Ring;
  /** Busy = disabled + spinner (§8.1). */
  busy: boolean;
  actionable: boolean;
}

const APPEARANCE: Record<VoicePageState, StateAppearance> = {
  idle: { icon: Microphone, label: '開始說話', fill: 'primary', ring: 'none', busy: false, actionable: true },
  recording: { icon: Stop, label: '說完了，按這裡', fill: 'accent', ring: 'breathing', busy: false, actionable: true },
  processingAsr: {
    icon: SpinnerGap,
    label: '請稍等一下',
    fill: 'primary',
    ring: 'none',
    busy: true,
    actionable: false,
  },
  generating: { icon: SpinnerGap, label: '請稍等一下', fill: 'primary', ring: 'none', busy: true, actionable: false },
  playing: { icon: SpeakerHigh, label: '正在說給你聽', fill: 'accent', ring: 'none', busy: true, actionable: false },
  lowConfidence: {
    icon: Microphone,
    label: '請先確認我聽到的話',
    fill: 'primary',
    ring: 'paused',
    busy: false,
    actionable: false,
  },
  timeout: { icon: ArrowClockwise, label: '再試一次', fill: 'primary', ring: 'paused', busy: false, actionable: true },
  offline: {
    icon: WifiSlash,
    label: '等網路回來再試',
    fill: 'primary',
    ring: 'paused',
    busy: false,
    actionable: false,
  },
  permissionDenied: {
    icon: MicrophoneSlash,
    label: '允許使用麥克風',
    fill: 'primary',
    ring: 'paused',
    busy: false,
    actionable: true,
  },
};

/** Full-sentence announcement (§1 狀態可感知, §13) — the visible label is shorter. */
const ARIA_LABEL: Record<VoicePageState, string> = {
  idle: '按一下開始說話',
  recording: '我在聽，說完了按一下結束',
  processingAsr: '我正在聽清楚你的話，請稍等',
  generating: '我正在整理回答，請稍等',
  playing: '我正在把回答說給你聽',
  lowConfidence: '請先確認我聽到的話',
  timeout: '剛剛沒有聽到聲音，按一下再試一次',
  offline: '網路好像斷了，等一下再試',
  permissionDenied: '要先讓我使用麥克風才能說話，按一下再允許一次',
};

export interface RecordButtonProps {
  state: VoicePageState;
  onPress: () => void;
  disabled?: boolean;
}

/** Single large primary action — the whole "low operational burden" entry point (A01.1). */
export function RecordButton({ state, onPress, disabled }: RecordButtonProps) {
  const appearance = APPEARANCE[state];
  const IconComponent = appearance.icon;
  const isDisabled = Boolean(disabled) || appearance.busy || !appearance.actionable;

  return (
    <div className={styles.wrapper}>
      {appearance.ring === 'breathing' && <span className={styles.ring} aria-hidden="true" />}
      {appearance.ring === 'paused' && <span className={styles.ringPaused} aria-hidden="true" />}
      <button
        type="button"
        onClick={onPress}
        disabled={isDisabled}
        aria-disabled={isDisabled}
        aria-busy={appearance.busy}
        aria-label={ARIA_LABEL[state]}
        className={`${styles.button} ${appearance.fill === 'accent' ? styles.fillAccent : styles.fillPrimary}`}
      >
        <IconComponent
          size={48}
          weight="fill"
          aria-hidden="true"
          className={appearance.busy && appearance.icon === SpinnerGap ? styles.spinner : undefined}
        />
        <span className={styles.label}>{appearance.label}</span>
      </button>
    </div>
  );
}
