import { describe, expect, it } from 'vitest';
import { pcmAudioStream } from './adapters.js';

describe('pcmAudioStream', () => {
  it('將 16 kHz 16-bit mono PCM 切成 100 ms chunks 且不遺失資料', async () => {
    // 16,000 samples/sec × 2 bytes/sample × 100 ms = 3,200 bytes/chunk。
    // 測試關閉等待，只驗證 deterministic 分塊，不讓單元測試真的暫停 100 ms。
    const source = Uint8Array.from({ length: 7_000 }, (_, index) => index % 251);
    const chunks: Uint8Array[] = [];

    for await (const event of pcmAudioStream(source, 16_000, 0)) {
      chunks.push(event.AudioEvent.AudioChunk);
    }

    expect(chunks.map((chunk) => chunk.byteLength)).toEqual([3_200, 3_200, 600]);
    expect(Uint8Array.from(chunks.flatMap((chunk) => [...chunk]))).toEqual(source);
  });

  it.each([0, -1, Number.NaN, Number.POSITIVE_INFINITY])(
    '拒絕不合法 sample rate：%s',
    async (sampleRate) => {
      const consume = async () => {
        for await (const _event of pcmAudioStream(new Uint8Array([0, 0]), sampleRate, 0)) {
          // generator 必須在產生任何 chunk 前拒絕不合法參數。
        }
      };
      await expect(consume()).rejects.toThrow('PCM sampleRate must be a positive finite number.');
    },
  );
});
