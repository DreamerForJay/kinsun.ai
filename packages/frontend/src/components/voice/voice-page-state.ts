import type { RecordingState } from '@elderly-care/shared';

/**
 * The 9 states design-system/MASTER.md §10.1 requires of the elder voice page.
 * `RecordingState` (shared) is the wire protocol the backend sends — only 4 of
 * these. The rest are resolved client-side: `offline` from navigator.onLine,
 * `timeout` from a local timer, `permissionDenied` from the recorder, and
 * `lowConfidence` from the server's ASR confirmation payload. Kept separate
 * from the shared type so the UI state machine can grow without changing a
 * backend contract.
 */
export type VoicePageState =
  | 'idle'
  | 'recording'
  | 'processingAsr'
  | 'generating'
  | 'playing'
  | 'lowConfidence'
  | 'timeout'
  | 'offline'
  | 'permissionDenied';

export function fromRecordingState(state: RecordingState): VoicePageState {
  switch (state) {
    case 'recording':
      return 'recording';
    case 'processing':
      return 'processingAsr';
    case 'playing':
      return 'playing';
    default:
      return 'idle';
  }
}

/** §10.1 copy. Subject is always the system — never "錯誤/失敗/無效" (§1). */
export const STATE_COPY: Record<VoicePageState, string> = {
  idle: '按一下開始說話',
  recording: '我在聽…',
  processingAsr: '我正在聽清楚你的話',
  generating: '我正在整理回答',
  playing: '我說完了，可以再聽一次',
  lowConfidence: '我聽到的可能不太準，想跟你確認一下',
  timeout: '剛剛沒有聽到聲音，要再試一次嗎？',
  offline: '網路好像斷了，等一下再試',
  permissionDenied: '要先讓我使用麥克風才能說話',
};

/** The 9 states, in §10.1 order — used by the dev-only preview switch. */
export const ALL_VOICE_PAGE_STATES: readonly VoicePageState[] = [
  'idle',
  'recording',
  'processingAsr',
  'generating',
  'playing',
  'lowConfidence',
  'timeout',
  'offline',
  'permissionDenied',
];

export function isVoicePageState(value: string): value is VoicePageState {
  return (ALL_VOICE_PAGE_STATES as readonly string[]).includes(value);
}
