import type { RecordingState } from '@elderly-care/shared';

/**
 * VoiceInteractionClient (design.md §前端層) — wraps MediaRecorder for
 * capture and HTMLAudioElement for playback. All browser-only; must only
 * be instantiated inside a 'use client' component.
 */
export class BrowserVoiceRecorder {
  private mediaRecorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private stream: MediaStream | null = null;
  private state: RecordingState = 'idle';
  private currentAudio: HTMLAudioElement | null = null;

  getRecordingState(): RecordingState {
    return this.state;
  }

  /** Returns false (instead of throwing) on denial so callers can show plain-language guidance (A01.3). */
  async requestMicPermission(): Promise<boolean> {
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      return true;
    } catch {
      return false;
    }
  }

  hasMicPermission(): boolean {
    return this.stream !== null;
  }

  async startRecording(): Promise<void> {
    if (!this.stream) {
      const granted = await this.requestMicPermission();
      if (!granted) throw new Error('MIC_PERMISSION_DENIED');
    }
    this.chunks = [];
    this.mediaRecorder = new MediaRecorder(this.stream!, { mimeType: 'audio/webm;codecs=opus' });
    this.mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) this.chunks.push(event.data);
    };
    this.mediaRecorder.start();
    this.state = 'recording';
  }

  async stopRecording(): Promise<Blob> {
    return new Promise((resolve) => {
      if (!this.mediaRecorder || this.mediaRecorder.state === 'inactive') {
        this.state = 'processing';
        resolve(new Blob(this.chunks, { type: 'audio/webm' }));
        return;
      }
      this.mediaRecorder.onstop = () => {
        this.state = 'processing';
        resolve(new Blob(this.chunks, { type: 'audio/webm' }));
      };
      this.mediaRecorder.stop();
    });
  }

  async playAudioFromUrl(url: string): Promise<void> {
    this.state = 'playing';
    try {
      await new Promise<void>((resolve, reject) => {
        const audio = new Audio(url);
        this.currentAudio = audio;
        audio.onended = () => resolve();
        audio.onerror = () => reject(new Error('AUDIO_PLAYBACK_FAILED'));
        void audio.play().catch(reject);
      });
    } finally {
      this.state = 'idle';
      this.currentAudio = null;
    }
  }

  setState(state: RecordingState): void {
    this.state = state;
  }

  stopPlayback(): void {
    this.currentAudio?.pause();
    this.currentAudio = null;
  }
}

export function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const result = reader.result as string;
      // Strip the "data:audio/webm;base64," prefix — only the payload goes over the wire.
      resolve(result.slice(result.indexOf(',') + 1));
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

/**
 * Sample rate the speech gateway transcribes at. MediaRecorder captures at the
 * device rate (usually 48 kHz), so the decoded audio is resampled rather than
 * merely reinterpreted — sending 48 kHz samples labelled as 16 kHz yields
 * confident-looking nonsense rather than an error.
 */
export const PCM_SAMPLE_RATE = 16000;

/**
 * Converts recorded audio (webm/opus from MediaRecorder) to 16-bit little-endian
 * mono PCM at PCM_SAMPLE_RATE.
 *
 * The conversion happens here rather than server-side because the browser
 * already ships an Opus decoder and a resampler in AudioContext; doing it in the
 * gateway would mean bundling a media decoder into the service image. Transcribe
 * streaming also accepts ogg-opus, but MediaRecorder emits a WebM container,
 * which is not interchangeable with Ogg.
 */
export async function blobToPcm16Base64(blob: Blob): Promise<string> {
  const encoded = await blob.arrayBuffer();

  // decodeAudioData needs a context to decode with, but the OfflineAudioContext
  // that performs the resampling must be created at the target rate.
  const decodeContext = new AudioContext();
  let decoded: AudioBuffer;
  try {
    decoded = await decodeContext.decodeAudioData(encoded);
  } finally {
    void decodeContext.close();
  }

  const frameCount = Math.max(
    1,
    Math.ceil(decoded.duration * PCM_SAMPLE_RATE),
  );
  const offline = new OfflineAudioContext(1, frameCount, PCM_SAMPLE_RATE);
  const source = offline.createBufferSource();
  source.buffer = decoded;
  source.connect(offline.destination);
  source.start();
  const resampled = await offline.startRendering();

  const samples = resampled.getChannelData(0);
  const pcm = new DataView(new ArrayBuffer(samples.length * 2));
  for (let index = 0; index < samples.length; index += 1) {
    // Clamp before scaling: decoded float samples can exceed ±1.0 slightly and
    // wrapping would turn a loud syllable into a click.
    const clamped = Math.max(-1, Math.min(1, samples[index]));
    pcm.setInt16(index * 2, Math.round(clamped * 0x7fff), true);
  }

  return arrayBufferToBase64(pcm.buffer);
}

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  // Chunked so a long utterance cannot exceed the argument limit of
  // String.fromCharCode via spread.
  const CHUNK = 0x8000;
  let binary = '';
  for (let offset = 0; offset < bytes.length; offset += CHUNK) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + CHUNK));
  }
  return btoa(binary);
}
