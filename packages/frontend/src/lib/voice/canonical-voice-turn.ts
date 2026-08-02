import type { ApiConfig } from '@/lib/api/client';
import { createVoiceSession, runCompanionTurn } from '@/lib/api/companion';
import { blobToPcm16Base64 } from './recorder';
import {
  canSynthesize,
  LanguageUnavailableError,
  synthesizeSpeech,
  transcribeAudio,
  type SpeechLanguage,
} from './speech-gateway-client';

/**
 * One spoken turn on the canonical path:
 *
 *   recorded audio -> speech gateway
 *                      zh-TW / en-US  -> Amazon Transcribe
 *                      nan-TW / hak-TW -> self-hosted SageMaker ASR
 *                  -> Core companion turn (agent-runtime: multi-agent + RAG + Bedrock)
 *                  -> speech gateway (Polly) -> playable audio, when available
 *
 * The reply path is identical for every language: Hokkien and Hakka differ only
 * in which model transcribes the audio. Synthesis is the one asymmetry — no
 * Hokkien/Hakka TTS endpoint is deployed, so those replies are shown as text.
 *
 * Core sits in the middle deliberately. The gateway holds no state and makes no
 * care decisions, so consent, session state and the record of what was said are
 * established by Core on the companion-turn call, not by the fact that audio was
 * successfully transcribed.
 */

export interface VoiceTurnTranscription {
  text: string;
  confidence: number;
  /** False means: ask the elder to confirm or repeat. Never act on the text. */
  acceptable: boolean;
}

export interface VoiceTurnReply {
  replyText: string;
  /** Null when synthesis is unavailable for the language or failed; the reply
   *  text is still shown rather than the turn being lost (A03.4). */
  audioUrl: string | null;
  /** True when the language has no synthesis model, so the UI can explain that
   *  the reply is text rather than implying playback failed. */
  textOnlyByLanguage: boolean;
  resultStatus: string;
  safetyDecision: string;
}

export class VoiceTurnError extends Error {
  constructor(
    public readonly stage: 'transcription' | 'language' | 'session' | 'companion',
    message: string,
  ) {
    super(message);
    this.name = 'VoiceTurnError';
  }
}

export async function transcribeTurn(
  audio: Blob,
  language: SpeechLanguage = 'zh-TW',
): Promise<VoiceTurnTranscription> {
  let pcmBase64: string;
  try {
    pcmBase64 = await blobToPcm16Base64(audio);
  } catch {
    throw new VoiceTurnError('transcription', 'could not decode the recorded audio');
  }

  try {
    const result = await transcribeAudio(pcmBase64, language);
    return {
      text: result.text,
      confidence: result.confidence,
      // An empty transcript is unusable regardless of the reported score: silence
      // must not be forwarded as if the elder had spoken.
      acceptable: result.confidenceAcceptable && result.text.trim() !== '',
    };
  } catch (cause) {
    if (cause instanceof LanguageUnavailableError) {
      // Distinguished from a failure so the elder is told this language is not
      // available rather than being asked to repeat themselves pointlessly.
      throw new VoiceTurnError('language', 'this language is not available yet');
    }
    throw new VoiceTurnError('transcription', 'speech recognition is unavailable');
  }
}

/**
 * Sends confirmed text through Core and returns the reply, spoken when possible.
 *
 * A fresh session per turn matches what Core's state machine expects — a
 * companion turn requires a newly created session — and keeps each utterance
 * individually auditable.
 */
export async function speakTurn(
  apiConfig: ApiConfig,
  elderId: string,
  confirmedText: string,
  language: SpeechLanguage,
): Promise<VoiceTurnReply> {
  let sessionId: string;
  try {
    sessionId = (await createVoiceSession(apiConfig, elderId, language)).session_id;
  } catch {
    throw new VoiceTurnError('session', 'could not start a voice session');
  }

  let turn: Awaited<ReturnType<typeof runCompanionTurn>>;
  try {
    turn = await runCompanionTurn(apiConfig, sessionId, confirmedText);
  } catch {
    throw new VoiceTurnError('companion', 'the companion service is unavailable');
  }

  const synthesizable = canSynthesize(language);
  let audioUrl: string | null = null;
  if (synthesizable) {
    // Synthesis is an enhancement, not the answer. If Polly fails the elder
    // still gets the reply on screen rather than a dead turn (A03.4).
    try {
      const audio = await synthesizeSpeech(turn.reply_text, language);
      audioUrl = audioBase64ToUrl(audio.audioBase64, audio.contentType);
    } catch {
      audioUrl = null;
    }
  }

  return {
    replyText: turn.reply_text,
    audioUrl,
    textOnlyByLanguage: !synthesizable,
    resultStatus: turn.result_status,
    safetyDecision: turn.safety_decision,
  };
}

function audioBase64ToUrl(audioBase64: string, contentType: string): string {
  const binary = atob(audioBase64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return URL.createObjectURL(new Blob([bytes], { type: contentType }));
}
