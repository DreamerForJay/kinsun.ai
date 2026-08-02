import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  canSynthesize: vi.fn(),
  createVoiceSession: vi.fn(),
  runCompanionTurn: vi.fn(),
  synthesizeSpeech: vi.fn(),
}));

vi.mock('@/lib/api/companion', () => ({
  createVoiceSession: mocks.createVoiceSession,
  runCompanionTurn: mocks.runCompanionTurn,
}));

vi.mock('./recorder', () => ({
  blobToPcm16Base64: vi.fn(),
}));

vi.mock('./speech-gateway-client', () => ({
  canSynthesize: mocks.canSynthesize,
  LanguageUnavailableError: class LanguageUnavailableError extends Error {},
  synthesizeSpeech: mocks.synthesizeSpeech,
  transcribeAudio: vi.fn(),
}));

import { speakTurn } from './canonical-voice-turn';

const config = { apiBaseUrl: '/backend/core' };

beforeEach(() => {
  mocks.canSynthesize.mockReset().mockImplementation((language: string) => language === 'zh-TW' || language === 'en-US');
  mocks.createVoiceSession.mockReset().mockResolvedValue({ session_id: 'session-1' });
  mocks.runCompanionTurn.mockReset().mockResolvedValue({
    reply_text: '安全的合成回覆',
    result_status: 'SUCCESS',
    safety_decision: 'ALLOW',
  });
  mocks.synthesizeSpeech.mockReset().mockResolvedValue({
    audioBase64: '',
    contentType: 'audio/mpeg',
  });
});

describe('speakTurn', () => {
  it('passes the selected language to the Core voice session and TTS', async () => {
    const objectUrl = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:synthetic-audio');

    await speakTurn(config, 'elder-1', 'Hello', 'en-US');

    expect(mocks.createVoiceSession).toHaveBeenCalledWith(config, 'elder-1', 'en-US');
    expect(mocks.synthesizeSpeech).toHaveBeenCalledWith('安全的合成回覆', 'en-US');
    objectUrl.mockRestore();
  });

  it.each(['nan-TW', 'hak-TW'] as const)(
    'keeps %s replies text-only without requesting TTS',
    async (language) => {
      const reply = await speakTurn(config, 'elder-1', '合成測試文字', language);

      expect(mocks.createVoiceSession).toHaveBeenCalledWith(config, 'elder-1', language);
      expect(mocks.synthesizeSpeech).not.toHaveBeenCalled();
      expect(reply).toMatchObject({ audioUrl: null, textOnlyByLanguage: true });
    },
  );
});
