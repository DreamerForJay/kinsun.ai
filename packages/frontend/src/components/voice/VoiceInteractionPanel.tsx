'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { ApiConfig } from '@/lib/api/client';
import { BrowserVoiceRecorder } from '@/lib/voice/recorder';
import { speakTurn, transcribeTurn, VoiceTurnError } from '@/lib/voice/canonical-voice-turn';
import type { SpeechLanguage } from '@/lib/voice/speech-gateway-client';
import { CompanionCharacter, type ConversationState } from './CompanionCharacter';
import { LanguageSelect } from './LanguageSelect';
import { readDevPreviewState } from './dev-preview';
import { LowConfidenceCard } from './LowConfidenceCard';
import { MicPermissionGuide } from './MicPermissionGuide';
import { RecordButton } from './RecordButton';
import { STATE_COPY, type VoicePageState } from './voice-page-state';

const DEFAULT_GREETING = '你好啊！今天想聊什麼呢？';

/** §10.1 Timeout: nothing came back after we said we were listening. */
const ASR_TIMEOUT_MS = 10_000;

/** Placeholder shown only by the dev preview, so the card has something to quote. */
const PREVIEW_TRANSCRIPT = '我今天早上有吃藥';

/** States where a turn is in flight, so the language must not be swapped. */
const busyStates = new Set<VoicePageState>(['processingAsr', 'generating', 'playing']);

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
  /** Elder hasn't granted recording consent yet — disables the mic entirely (A06.2). */
  consentGranted: boolean;
  /** Same-origin BFF config; the panel never holds a bearer token itself. */
  apiConfig: ApiConfig;
  elderId: string;
}

export function VoiceInteractionPanel({
  apiConfig,
  elderId,
  consentGranted,
}: VoiceInteractionPanelProps) {
  const [state, setState] = useState<VoicePageState>('idle');
  const [previewState, setPreviewState] = useState<VoicePageState | null>(null);
  const [displayText, setDisplayText] = useState('');
  const [transcript, setTranscript] = useState('');
  const [pendingTranscript, setPendingTranscript] = useState('');
  const [errorText, setErrorText] = useState('');
  const [noticeText, setNoticeText] = useState('');
  const [language, setLanguage] = useState<SpeechLanguage>('zh-TW');

  const recorderRef = useRef<BrowserVoiceRecorder | null>(null);
  const audioUrlRef = useRef<string | null>(null);

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
    // Preview renders states only — no microphone, no recording.
    if (isPreview) return;
    recorderRef.current = new BrowserVoiceRecorder();
  }, [consentGranted, isPreview]);

  // Object URLs from synthesized audio are revoked on unmount so a long session
  // does not accumulate audio blobs in memory.
  useEffect(
    () => () => {
      if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current);
    },
    [],
  );

  /**
   * Sends confirmed text to Core and plays the spoken reply.
   *
   * Only reached with a transcript the elder either spoke clearly or explicitly
   * confirmed — recognition alone never triggers this.
   */
  const runCompanion = useCallback(
    async (confirmedText: string) => {
      setState('generating');
      try {
        const reply = await speakTurn(apiConfig, elderId, confirmedText);
        setDisplayText(reply.replyText);

        if (reply.textOnlyByLanguage) {
          // Said explicitly rather than leaving the elder waiting for a voice
          // that is never coming.
          setNoticeText('這個語言的回答目前只能用文字顯示。');
        }

        if (reply.audioUrl) {
          if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current);
          audioUrlRef.current = reply.audioUrl;
          setState('playing');
          await recorderRef.current?.playAudioFromUrl(reply.audioUrl);
        }
        setState('idle');
      } catch (cause) {
        // The reply is not shown as something the elder got wrong: a companion
        // failure is a service problem, and the utterance was not stored.
        setErrorText(
          cause instanceof VoiceTurnError && cause.stage === 'companion'
            ? '陪伴服務暫時沒有回應，請稍後再試。'
            : '目前無法開始這次對話，請稍後再試。',
        );
        setState('idle');
      }
    },
    [apiConfig, elderId],
  );

  const beginRecording = useCallback(async () => {
    const recorder = recorderRef.current;
    if (!recorder) return;

    const granted = recorder.hasMicPermission() || (await recorder.requestMicPermission());
    if (!granted) {
      setState('permissionDenied');
      return;
    }
    setDisplayText('');
    setTranscript('');
    setPendingTranscript('');
    setErrorText('');
    setNoticeText('');
    await recorder.startRecording();
    setState('recording');
  }, []);

  const handlePress = useCallback(async () => {
    const recorder = recorderRef.current;
    if (!recorder) return;

    if (state === 'idle' || state === 'timeout' || state === 'permissionDenied') {
      await beginRecording();
      return;
    }

    if (state !== 'recording') return;

    const blob = await recorder.stopRecording();
    setState('processingAsr');
    try {
      const result = await transcribeTurn(blob, language);
      if (!result.acceptable) {
        // ASR must not pretend it understood (AGENTS.md §3). Low confidence goes
        // to the elder for confirmation instead of into the companion turn.
        // An empty transcript has nothing to confirm, so that resets instead.
        if (result.text.trim() === '') {
          setErrorText('剛剛沒有聽到聲音，請再說一次。');
          setState('idle');
          return;
        }
        setPendingTranscript(result.text);
        setState('lowConfidence');
        return;
      }
      setTranscript(result.text);
      await runCompanion(result.text);
    } catch (cause) {
      const stage = cause instanceof VoiceTurnError ? cause.stage : null;
      setErrorText(
        stage === 'language'
          ? // Not "please repeat": repeating cannot help when no model exists.
            '這個語言目前還沒辦法辨識，請先改用國語。'
          : stage === 'transcription'
            ? '目前無法辨識語音，請稍後再試。'
            : '目前無法處理這次語音，請稍後再試。',
      );
      setState('idle');
    }
  }, [state, beginRecording, runCompanion, language]);

  // The three handlers also drop any preview override, so the full-screen card
  // stays dismissible when a reviewer opened it via ?previewState=lowConfidence.
  const handleConfirmTranscript = useCallback(() => {
    setPreviewState(null);
    const confirmed = pendingTranscript;
    setTranscript(confirmed);
    setPendingTranscript('');
    // The elder confirming the transcript is what authorizes acting on it, so
    // the companion turn starts here rather than when recognition returned.
    if (confirmed.trim() !== '') void runCompanion(confirmed);
    else setState('idle');
  }, [pendingTranscript, runCompanion]);

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

      <LanguageSelect
        language={language}
        onChange={setLanguage}
        // Changing language mid-turn would leave an utterance being transcribed
        // by one model and attributed to another.
        disabled={effectiveState === 'recording' || busyStates.has(effectiveState)}
      />

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

      {errorText !== '' && (
        <p
          role="alert"
          style={{
            margin: 0,
            maxWidth: '32ch',
            textAlign: 'center',
            fontSize: 'var(--text-base)',
            lineHeight: 'var(--leading-body)',
            color: 'var(--color-destructive)',
          }}
        >
          {errorText}
        </p>
      )}

      {/* Not an error — the reply arrived, it just cannot be spoken yet. */}
      {noticeText !== '' && errorText === '' && (
        <p
          aria-live="polite"
          style={{
            margin: 0,
            maxWidth: '32ch',
            textAlign: 'center',
            fontSize: 'var(--text-sm)',
            lineHeight: 'var(--leading-body)',
            color: 'var(--color-muted-foreground)',
          }}
        >
          {noticeText}
        </p>
      )}

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
