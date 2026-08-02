'use client';

/**
 * Local speech check page.
 *
 * Exists to verify the browser -> speech gateway -> Transcribe/Polly path with a
 * real microphone, independent of the consent gate and voice session state
 * machine. It records nothing beyond the current utterance and stores nothing:
 * this is a wiring check, not a product surface.
 *
 * Returns 404 outside development so it cannot become a way to capture an
 * elder's voice without going through Core's consent gate.
 */

import { useCallback, useRef, useState } from 'react';
import { BrowserVoiceRecorder, blobToPcm16Base64 } from '@/lib/voice/recorder';
import {
  audioBase64ToObjectUrl,
  canSynthesize,
  LanguageUnavailableError,
  synthesizeSpeech,
  transcribeAudio,
  type SpeechLanguage,
} from '@/lib/voice/speech-gateway-client';

type Language = SpeechLanguage;

const LANGUAGES: { value: Language; label: string }[] = [
  { value: 'zh-TW', label: '國語 (Transcribe)' },
  { value: 'nan-TW', label: '台語 (SageMaker)' },
  { value: 'hak-TW', label: '客語 (SageMaker)' },
  { value: 'en-US', label: 'English (Transcribe)' },
];

export default function DevSpeechPage() {
  const recorderRef = useRef<BrowserVoiceRecorder | null>(null);
  const [language, setLanguage] = useState<Language>('zh-TW');
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [confidence, setConfidence] = useState<number | null>(null);
  const [acceptable, setAcceptable] = useState<boolean | null>(null);
  const [error, setError] = useState('');
  const [ttsText, setTtsText] = useState('阿嬤您好，今天有沒有吃飯？');

  const start = useCallback(async () => {
    setError('');
    setTranscript('');
    setConfidence(null);
    setAcceptable(null);
    try {
      const recorder = recorderRef.current ?? new BrowserVoiceRecorder();
      recorderRef.current = recorder;
      await recorder.startRecording();
      setRecording(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'could not start recording');
    }
  }, []);

  const stop = useCallback(async () => {
    const recorder = recorderRef.current;
    if (!recorder) return;
    setRecording(false);
    setBusy(true);
    try {
      const blob = await recorder.stopRecording();
      const pcm = await blobToPcm16Base64(blob);
      const result = await transcribeAudio(pcm, language);
      setTranscript(result.text);
      setConfidence(result.confidence);
      setAcceptable(result.confidenceAcceptable);
    } catch (cause) {
      setError(
        cause instanceof LanguageUnavailableError
          ? `${language}: no model deployed for this language`
          : cause instanceof Error
            ? cause.message
            : 'transcription failed',
      );
    } finally {
      setBusy(false);
    }
  }, [language]);

  const speak = useCallback(async () => {
    setError('');
    if (!canSynthesize(language)) {
      setError(`${language}: no TTS endpoint deployed for this language yet`);
      return;
    }
    setBusy(true);
    try {
      const result = await synthesizeSpeech(ttsText, language);
      const url = audioBase64ToObjectUrl(result.audioBase64, result.contentType);
      const audio = new Audio(url);
      audio.onended = () => URL.revokeObjectURL(url);
      await audio.play();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'synthesis failed');
    } finally {
      setBusy(false);
    }
  }, [ttsText, language]);

  return (
    <main style={{ padding: 32, maxWidth: 720, fontFamily: 'system-ui, sans-serif' }}>
      <h1 style={{ fontSize: 24, marginBottom: 4 }}>Speech gateway check</h1>
      <p style={{ color: '#666', marginBottom: 24 }}>
        Browser → speech-gateway → Amazon Transcribe / Polly. Development only.
      </p>

      <fieldset style={{ marginBottom: 24, border: '1px solid #ddd', padding: 16 }}>
        <legend>Language</legend>
        {LANGUAGES.map((option) => (
          <label key={option.value} style={{ marginRight: 16, whiteSpace: 'nowrap' }}>
            <input
              type="radio"
              name="language"
              value={option.value}
              checked={language === option.value}
              onChange={() => setLanguage(option.value)}
            />{' '}
            {option.label}
          </label>
        ))}
        {!canSynthesize(language) && (
          <p style={{ margin: '12px 0 0', color: '#666', fontSize: 14 }}>
            ASR only — no TTS endpoint is deployed for this language.
          </p>
        )}
      </fieldset>

      <section style={{ marginBottom: 32 }}>
        <h2 style={{ fontSize: 18 }}>ASR — speak into the microphone</h2>
        <button
          type="button"
          onClick={recording ? stop : start}
          disabled={busy}
          style={{
            padding: '12px 24px',
            fontSize: 16,
            background: recording ? '#c0392b' : '#2c7',
            color: '#fff',
            border: 'none',
            borderRadius: 6,
            cursor: busy ? 'wait' : 'pointer',
          }}
        >
          {recording ? '停止並辨識' : busy ? '處理中…' : '開始錄音'}
        </button>

        {transcript !== '' && (
          <div style={{ marginTop: 16, padding: 16, background: '#f6f6f6', borderRadius: 6 }}>
            <p style={{ margin: 0, fontSize: 18 }}>{transcript}</p>
            <p style={{ margin: '8px 0 0', color: '#666', fontSize: 14 }}>
              confidence {confidence?.toFixed(4)}
              {acceptable === false && (
                <strong style={{ color: '#c0392b' }}> — 低於門檻，需請長者再說一次</strong>
              )}
            </p>
          </div>
        )}
      </section>

      <section>
        <h2 style={{ fontSize: 18 }}>TTS — synthesize and play</h2>
        <textarea
          value={ttsText}
          onChange={(event) => setTtsText(event.target.value)}
          rows={3}
          style={{ width: '100%', padding: 8, fontSize: 15, fontFamily: 'inherit' }}
        />
        <button
          type="button"
          onClick={speak}
          disabled={busy || ttsText.trim() === ''}
          style={{
            marginTop: 8,
            padding: '12px 24px',
            fontSize: 16,
            background: '#36c',
            color: '#fff',
            border: 'none',
            borderRadius: 6,
            cursor: busy ? 'wait' : 'pointer',
          }}
        >
          {busy ? '處理中…' : '播放'}
        </button>
      </section>

      {error !== '' && (
        <p style={{ marginTop: 24, color: '#c0392b' }} role="alert">
          {error}
        </p>
      )}
    </main>
  );
}
