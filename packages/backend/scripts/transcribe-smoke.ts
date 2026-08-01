import { readFile } from 'node:fs/promises';
import { performance } from 'node:perf_hooks';
import { TranscribeAdapter } from '../src/asr/adapters.js';

const argumentsSet = new Set(process.argv.slice(2));
const audioFlagIndex = process.argv.indexOf('--audio');
const pcmPath = audioFlagIndex >= 0 ? process.argv[audioFlagIndex + 1] : undefined;

if (!argumentsSet.has('--synthetic') || !pcmPath) {
  throw new Error(
    'Usage: npm run smoke:transcribe -- --audio <synthetic.pcm> --synthetic',
  );
}

const audio = await readFile(pcmPath);
console.log(`準備送出 ${audio.byteLength} bytes 的 Synthetic PCM 音訊`);

const adapter = new TranscribeAdapter();
const started = performance.now();

try {
  const result = await adapter.transcribe(
    { data: audio, encoding: 'pcm', sampleRate: 16_000 },
    'zh-TW',
  );
  // 此指令只供受控 Synthetic 評測，輸出不得轉送一般 production Log。
  console.log({
    text: result.text,
    confidence: result.confidence,
    modelVersion: result.modelVersion,
    segments: result.segments,
    latencyMs: Math.round(performance.now() - started),
  });
} catch (error) {
  console.error('Transcribe Synthetic smoke test 失敗');
  console.error(error instanceof Error ? error.message : 'Unknown error');
  process.exitCode = 1;
}
