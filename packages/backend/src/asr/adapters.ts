import {
  LanguageCode,
  TranscribeStreamingClient,
  StartStreamTranscriptionCommand,
} from '@aws-sdk/client-transcribe-streaming';
import { InvokeEndpointCommand, SageMakerRuntimeClient } from '@aws-sdk/client-sagemaker-runtime';
import type { AudioInput, ConcreteLanguage, TranscriptSegment } from './types.js';

export interface AdapterResult {
  text: string;
  confidence: number;
  modelVersion: string;
  segments: TranscriptSegment[];
}

export interface AsrAdapter {
  transcribe(audio: AudioInput, language: ConcreteLanguage): Promise<AdapterResult>;
}

const TRANSCRIBE_LANGUAGE_CODES: Record<'zh-TW' | 'en-US', LanguageCode> = {
  'zh-TW': LanguageCode.ZH_TW,
  'en-US': LanguageCode.EN_US,
};

/**
 * Bytes per AudioEvent. Transcribe rejects the entire request with
 * "Your stream is too big. Reduce the frame size and try your request again."
 * once a single event exceeds its frame limit, so even a short utterance cannot
 * be sent as one chunk.
 *
 * 3200 bytes is 100ms of 16kHz 16-bit mono PCM. It stays a safe frame size for
 * higher sample rates and for ogg-opus as well — those simply carry a different
 * amount of audio per frame, which the service reassembles from the byte
 * sequence either way.
 */
const AUDIO_FRAME_BYTES = 3200;

/**
 * Splits the utterance into Transcribe-sized frames. The streaming API expects
 * a sequence of small frames rather than one blob — this is why the recorded
 * audio is re-chunked here instead of being forwarded as-is.
 */
async function* framedAudioStream(data: Uint8Array, frameBytes = AUDIO_FRAME_BYTES) {
  for (let offset = 0; offset < data.length; offset += frameBytes) {
    yield { AudioEvent: { AudioChunk: data.subarray(offset, offset + frameBytes) } };
  }
}

/** AWS Transcribe Streaming — handles Mandarin and English (A02.1, A02.3). */
export class TranscribeAdapter implements AsrAdapter {
  constructor(private readonly client: TranscribeStreamingClient = new TranscribeStreamingClient({})) {}

  async transcribe(audio: AudioInput, language: 'zh-TW' | 'en-US'): Promise<AdapterResult> {
    const command = new StartStreamTranscriptionCommand({
      LanguageCode: TRANSCRIBE_LANGUAGE_CODES[language],
      MediaEncoding: audio.encoding === 'opus' ? 'ogg-opus' : 'pcm',
      MediaSampleRateHertz: audio.sampleRate,
      AudioStream: framedAudioStream(audio.data),
    });
    const response = await this.client.send(command);

    let text = '';
    let confidence = 1;
    const segments: TranscriptSegment[] = [];

    if (response.TranscriptResultStream) {
      for await (const event of response.TranscriptResultStream) {
        const results = event.TranscriptEvent?.Transcript?.Results ?? [];
        for (const result of results) {
          if (result.IsPartial) continue;
          const alt = result.Alternatives?.[0];
          if (!alt?.Transcript) continue;
          text += alt.Transcript;
          const items = alt.Items ?? [];
          const confidences = items.map((i) => i.Confidence ?? 1);
          const segmentConfidence = confidences.length
            ? confidences.reduce((a, b) => a + b, 0) / confidences.length
            : 1;
          confidence = Math.min(confidence, segmentConfidence);
          segments.push({
            text: alt.Transcript,
            startTime: result.StartTime ?? 0,
            endTime: result.EndTime ?? 0,
            confidence: segmentConfidence,
            language,
          });
        }
      }
    }

    return { text, confidence, modelVersion: 'aws-transcribe-streaming', segments };
  }
}

/** Pre-deployed SageMaker endpoint — handles Hokkien and Hakka (A02.1, A02.3). */
export class SageMakerAdapter implements AsrAdapter {
  constructor(
    private readonly endpointName: string = process.env.ASR_SAGEMAKER_ENDPOINT ?? '',
    private readonly client: SageMakerRuntimeClient = new SageMakerRuntimeClient({}),
  ) {}

  async transcribe(audio: AudioInput, language: 'nan-TW' | 'hak-TW'): Promise<AdapterResult> {
    if (!this.endpointName) {
      throw new Error('ASR_SAGEMAKER_ENDPOINT is not configured');
    }
    const response = await this.client.send(
      new InvokeEndpointCommand({
        EndpointName: this.endpointName,
        ContentType: 'application/octet-stream',
        Body: audio.data,
        CustomAttributes: JSON.stringify({ language, sampleRate: audio.sampleRate }),
      }),
    );
    const payload = response.Body ? JSON.parse(Buffer.from(response.Body).toString('utf-8')) : {};
    const text: string = payload.text ?? '';
    const confidence: number = payload.confidence ?? 0;
    return {
      text,
      confidence,
      modelVersion: response.CustomAttributes ?? 'unknown',
      segments: [{ text, startTime: 0, endTime: 0, confidence, language }],
    };
  }
}
