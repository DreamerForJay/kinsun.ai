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

const PCM_BYTES_PER_SAMPLE = 2;
const STREAM_CHUNK_DURATION_MS = 100;

const wait = (milliseconds: number) =>
  new Promise<void>((resolve) => setTimeout(resolve, milliseconds));

async function* singleChunkAudioStream(data: Uint8Array) {
  yield { AudioEvent: { AudioChunk: data } };
}

export async function* pcmAudioStream(
  data: Uint8Array,
  sampleRate: number,
  chunkDelayMilliseconds = STREAM_CHUNK_DURATION_MS,
) {
  // PCM 契約是單聲道 16-bit little-endian；新增雙聲道時必須同步納入聲道數。
  if (!Number.isFinite(sampleRate) || sampleRate <= 0) {
    throw new RangeError('PCM sampleRate must be a positive finite number.');
  }
  const bytesPerSecond = sampleRate * PCM_BYTES_PER_SAMPLE;
  const chunkSize = Math.floor((bytesPerSecond * STREAM_CHUNK_DURATION_MS) / 1000);

  for (let offset = 0; offset < data.byteLength; offset += chunkSize) {
    const end = Math.min(offset + chunkSize, data.byteLength);
    yield { AudioEvent: { AudioChunk: data.subarray(offset, end) } };
    if (end < data.byteLength && chunkDelayMilliseconds > 0) {
      await wait(chunkDelayMilliseconds);
    }
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
      // PCM 依實際音訊時間分塊送出；Opus byte rate 不可套用 PCM 算式。
      AudioStream:
        audio.encoding === 'pcm'
          ? pcmAudioStream(audio.data, audio.sampleRate)
          : singleChunkAudioStream(audio.data),
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
