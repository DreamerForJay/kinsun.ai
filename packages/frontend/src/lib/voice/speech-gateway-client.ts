import { PCM_SAMPLE_RATE } from './recorder';

/**
 * Client for the speech gateway (services/speech-gateway).
 *
 * The gateway converts audio to text and text to audio. It holds no state and
 * makes no care decisions, so a successful transcription here is not permission
 * to act on what was said — consent and voice-session state still live in Core.
 */

/** Languages the gateway can transcribe. Mandarin/English via Amazon Transcribe,
 *  Hokkien/Hakka via the self-hosted SageMaker endpoint. */
export type SpeechLanguage = 'zh-TW' | 'en-US' | 'nan-TW' | 'hak-TW';

/** Synthesis covers Mandarin and English only — no Hokkien/Hakka TTS endpoint
 *  is deployed yet, so those replies are shown as text. */
export type SynthesisLanguage = 'zh-TW' | 'en-US';

const SYNTHESIS_LANGUAGE_ALLOWLIST: ReadonlySet<SpeechLanguage> = new Set([
  'zh-TW',
  'en-US',
]);

export function canSynthesize(language: SpeechLanguage): language is SynthesisLanguage {
  return SYNTHESIS_LANGUAGE_ALLOWLIST.has(language);
}

export interface TranscriptionResult {
  text: string;
  confidence: number;
  /**
   * False means the utterance was not recognised well enough to act on. The
   * caller must ask the elder to confirm or repeat rather than proceeding, which
   * is why this is a decision from the gateway and not a raw score the UI has to
   * re-threshold.
   */
  confidenceAcceptable: boolean;
  language: SpeechLanguage;
}

/** The gateway answers 501 when this deployment has no model for the language,
 *  which is different from a model that failed and is surfaced separately. */
export class LanguageUnavailableError extends Error {
  constructor(public readonly language: SpeechLanguage) {
    super(`no speech model is available for ${language}`);
    this.name = 'LanguageUnavailableError';
  }
}

export interface SynthesisResult {
  audioBase64: string;
  contentType: string;
}

function gatewayBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_SPEECH_GATEWAY_URL;
  if (!configured) throw new Error('NEXT_PUBLIC_SPEECH_GATEWAY_URL is not configured');
  return configured.replace(/\/+$/, '');
}

export async function transcribeAudio(
  audioBase64: string,
  language: SpeechLanguage,
): Promise<TranscriptionResult> {
  const response = await fetch(`${gatewayBaseUrl()}/api/v1/speech/transcriptions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      audio_base64: audioBase64,
      language,
      sample_rate: PCM_SAMPLE_RATE,
      encoding: 'pcm',
    }),
  });

  if (response.status === 501) {
    throw new LanguageUnavailableError(language);
  }
  if (!response.ok) {
    throw new Error(`transcription failed with ${response.status}`);
  }

  const body = (await response.json()) as {
    text: string;
    confidence: number;
    confidence_acceptable: boolean;
    language: SpeechLanguage;
  };

  return {
    text: body.text,
    confidence: body.confidence,
    confidenceAcceptable: body.confidence_acceptable,
    language: body.language,
  };
}

export async function synthesizeSpeech(
  text: string,
  language: SynthesisLanguage,
  speakingSpeed: 'slow' | 'normal' | 'fast' = 'normal',
): Promise<SynthesisResult> {
  const response = await fetch(`${gatewayBaseUrl()}/api/v1/speech/syntheses`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, language, speaking_speed: speakingSpeed }),
  });

  if (!response.ok) {
    throw new Error(`synthesis failed with ${response.status}`);
  }

  const body = (await response.json()) as { audio_base64: string; content_type: string };
  return { audioBase64: body.audio_base64, contentType: body.content_type };
}

/** Playable object URL for synthesized audio, for HTMLAudioElement playback. */
export function audioBase64ToObjectUrl(audioBase64: string, contentType: string): string {
  const binary = atob(audioBase64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return URL.createObjectURL(new Blob([bytes], { type: contentType }));
}
