'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { blobToBase64, BrowserVoiceRecorder } from '@/lib/voice/recorder';
import { VoiceWebSocketClient, type ServerResponsePayload } from '@/lib/voice/websocket-client';
import { CompanionCharacter, type ConversationState } from './CompanionCharacter';
import { readDevPreviewState } from './dev-preview';
import { LowConfidenceCard } from './LowConfidenceCard';
import { MicPermissionGuide } from './MicPermissionGuide';
import { RecordButton } from './RecordButton';
import { fromRecordingState, STATE_COPY, type VoicePageState } from './voice-page-state';

const DEFAULT_GREETING = '你好啊！今天想聊什麼呢？';

/** §10.1 Timeout: nothing came back after we said we were listening. */
const ASR_TIMEOUT_MS = 10_000;

/** Placeholder shown only by the dev preview, so the card has something to quote. */
const PREVIEW_TRANSCRIPT = '我今天早上有吃藥';

/**
 * The two fields the Low Confidence path needs. They are NOT part of
 * `ServerResponsePayload` because the backend does not emit them yet — so this
 * path currently only activates through the dev preview below. Nothing here is
 * wired end to end; do not read it as working ASR confirmation.
 */
interface LowConfidenceHints {
  lowConfidence?: boolean;
  transcriptCandidate?: string;
}

/** Maps the page state onto the companion's presentation states. */
function toConversationState(state: VoicePageState): ConversationState {
  switch (state) {
    case 'recording':
      return 'listening';
    case 'processingAsr':
    case 'generating':
    case 'lowConfidence':
      return 'processing';
    case 'playing':
      return 'speaking';
    case 'offline':
    case 'permissionDenied':
    case 'timeout':
      return 'sleeping';
    default:
      return 'idle';
  }
}

export interface VoiceInteractionPanelProps {
  wsUrl: string;
  /** Elder hasn't granted recording consent yet — disables the mic entirely (A06.2). */
  consentGranted: boolean;
  /** packages/backend's own Cognito JWT — a different credential from the BFF's HttpOnly cookie, see websocket-client.ts. */
  token: string;
}

export function VoiceInteractionPanel({ wsUrl, token, consentGranted }: VoiceInteractionPanelProps) {
  const [state, setState] = useState<VoicePageState>('idle');
  const [previewState, setPreviewState] = useState<VoicePageState | null>(null);
  const [displayText, setDisplayText] = useState('');
  const [transcript, setTranscript] = useState('');
  const [pendingTranscript, setPendingTranscript] = useState('');

  const recorderRef = useRef<BrowserVoiceRecorder | null>(null);
  const wsRef = useRef<VoiceWebSocketClient | null>(null);

  useEffect(() => {
    setPreviewState(readDevPreviewState());
  }, []);

  const isPreview = previewState !== null;
  const effectiveState: VoicePageState = previewState ?? state;

  /** §10.1 Offline — derived client-side from the browser, not from the server. */
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (!window.navigator.onLine) setState('offline');

    const handleOffline = () => setState('offline');
    const handleOnline = () => setState((current) => (current === 'offline' ? 'idle' : current));

    window.addEventListener('offline', handleOffline);
    window.addEventListener('online', handleOnline);
    return () => {
      window.removeEventListener('offline', handleOffline);
      window.removeEventListener('online', handleOnline);
    };
  }, []);

  /** §10.1 Timeout — a local timer, the server sends no such signal. */
  useEffect(() => {
    if (state !== 'processingAsr') return;
    const timer = window.setTimeout(() => {
      setState((current) => (current === 'processingAsr' ? 'timeout' : current));
    }, ASR_TIMEOUT_MS);
    return () => window.clearTimeout(timer);
  }, [state]);

  useEffect(() => {
    if (!consentGranted) return;
    // Preview renders states only — no socket, no microphone, no recording.
    if (isPreview) return;

    const recorder = new BrowserVoiceRecorder();
    const ws = new VoiceWebSocketClient();
    recorderRef.current = recorder;
    wsRef.current = ws;

    ws.onStateChange((s) => setState(fromRecordingState(s)));
    ws.onAudioResponse((payload: ServerResponsePayload) => {
      const hints = payload as ServerResponsePayload & LowConfidenceHints;
      const candidate = hints.transcriptCandidate ?? payload.transcript ?? '';

      if (hints.lowConfidence === true && candidate !== '') {
        // ASR must not pretend it understood (AGENTS.md §3) — ask first.
        setPendingTranscript(candidate);
        setState('lowConfidence');
        return;
      }

      setState('generating');
      if (payload.transcript) setTranscript(payload.transcript);
      if (payload.response) setDisplayText(payload.response);

      const play = async () => {
        if (payload.audioUrl) {
          setState('playing');
          await recorder.playAudioFromUrl(payload.audioUrl);
        }
        setState('idle');
      };
      void play();
    });

    ws.connect(wsUrl, token).catch(() => {
      setState('offline');
    });

    return () => {
      ws.disconnect();
    };
  }, [wsUrl, token, consentGranted, isPreview]);

  const beginRecording = useCallback(async () => {
    const recorder = recorderRef.current;
    const ws = wsRef.current;
    if (!recorder || !ws) return;

    const granted = recorder.hasMicPermission() || (await recorder.requestMicPermission());
    if (!granted) {
      setState('permissionDenied');
      return;
    }
    setDisplayText('');
    setTranscript('');
    setPendingTranscript('');
    ws.startSession();
    await recorder.startRecording();
    setState('recording');
  }, []);

  const handlePress = useCallback(async () => {
    const recorder = recorderRef.current;
    const ws = wsRef.current;
    if (!recorder || !ws) return;

    if (state === 'idle' || state === 'timeout' || state === 'permissionDenied') {
      await beginRecording();
      return;
    }

    if (state === 'recording') {
      const blob = await recorder.stopRecording();
      setState('processingAsr');
      const audioBase64 = await blobToBase64(blob);
      ws.sendAudio(audioBase64, 'opus', 48000);
      ws.stopSession();
    }
  }, [state, beginRecording]);

  // The three handlers also drop any preview override, so the full-screen card
  // stays dismissible when a reviewer opened it via ?previewState=lowConfidence.
  const handleConfirmTranscript = useCallback(() => {
    setPreviewState(null);
    setTranscript(pendingTranscript);
    setPendingTranscript('');
    setState('generating');
  }, [pendingTranscript]);

  const handleRetryTranscript = useCallback(() => {
    setPreviewState(null);
    setPendingTranscript('');
    setTranscript('');
    setState('idle');
  }, []);

  const handleDeferTranscript = useCallback(() => {
    // Nothing is kept pending — "稍後再說" must not quietly queue the utterance.
    setPreviewState(null);
    setPendingTranscript('');
    setState('idle');
  }, []);

  // The consent gate exists to stop recording without consent. The dev preview
  // records nothing: the effect above returns before constructing any
  // BrowserVoiceRecorder or VoiceWebSocketClient when isPreview, so no
  // microphone is opened and no audio leaves the page. Exempting it therefore
  // gives up no protection, and the gate still applies in full to every
  // non-preview render (and to all of production, where isPreview is always
  // false — see dev-preview.tsx).
  if (!consentGranted && !isPreview) {
    return (
      <p
        style={{
          textAlign: 'center',
          fontSize: 'var(--text-base)',
          lineHeight: 'var(--leading-body)',
          color: 'var(--color-muted-foreground)',
        }}
      >
        請先完成錄音同意設定，才能開始使用語音功能。
      </p>
    );
  }

  const companionMessage =
    effectiveState === 'idle' || effectiveState === 'playing'
      ? displayText || DEFAULT_GREETING
      : STATE_COPY[effectiveState];

  const cardTranscript = pendingTranscript || (isPreview ? PREVIEW_TRANSCRIPT : '');

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 'var(--block-gap)',
        width: '100%',
      }}
    >
      <CompanionCharacter state={toConversationState(effectiveState)} message={companionMessage} />

      <RecordButton state={effectiveState} onPress={handlePress} />

      {/* §1 狀態可感知 / §13 — the state is text, not only motion, and it is announced. */}
      <p
        aria-live="polite"
        style={{
          margin: 0,
          maxWidth: '32ch',
          textAlign: 'center',
          fontSize: 'var(--text-base)',
          lineHeight: 'var(--leading-body)',
          color: 'var(--color-foreground)',
        }}
      >
        {STATE_COPY[effectiveState]}
      </p>

      {effectiveState === 'permissionDenied' && <MicPermissionGuide onRetry={handlePress} />}

      {transcript && (
        <p
          style={{
            maxWidth: '32ch',
            textAlign: 'center',
            fontSize: 'var(--text-sm)',
            lineHeight: 'var(--leading-body)',
            color: 'var(--color-muted-foreground)',
          }}
        >
          您說：「{transcript}」
        </p>
      )}

      {effectiveState === 'lowConfidence' && cardTranscript !== '' && (
        <LowConfidenceCard
          transcript={cardTranscript}
          onConfirm={handleConfirmTranscript}
          onRetry={handleRetryTranscript}
          onDefer={handleDeferTranscript}
        />
      )}
    </div>
  );
}
