// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import { createElement } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  companionPanel: vi.fn(),
  getRuntimeConfig: vi.fn(),
  getVoiceSessionConfig: vi.fn(),
  listConsents: vi.fn(),
  voicePanel: vi.fn(),
}));

vi.mock('@/components/companion/CompanionTextPanel', () => ({
  CompanionTextPanel: mocks.companionPanel,
}));

vi.mock('@/lib/api/consent', () => ({
  activeBasicVoiceConsent: vi.fn(),
  listConsents: mocks.listConsents,
}));

vi.mock('@/lib/runtime-config', () => ({
  getRuntimeConfig: mocks.getRuntimeConfig,
  getVoiceSessionConfig: mocks.getVoiceSessionConfig,
}));

vi.mock('./dev-preview', () => ({
  readDevPreviewState: () => null,
}));

vi.mock('./VoiceInteractionPanel', () => ({
  VoiceInteractionPanel: mocks.voicePanel,
}));

import { VoiceHomeClient } from './VoiceHomeClient';

const unavailableConfig = {
  apiBaseUrl: '/backend/core',
  elderId: '',
  caregiverId: '',
  consentPolicyVersion: 'synthetic-policy-v1',
  credentialStatus: 'unavailable' as const,
};

beforeEach(() => {
  mocks.companionPanel.mockReset().mockReturnValue(null);
  mocks.getRuntimeConfig.mockReset();
  mocks.getVoiceSessionConfig.mockReset().mockReturnValue({ wsUrl: '', token: '' });
  mocks.listConsents.mockReset();
  mocks.voicePanel.mockReset().mockReturnValue(null);
});

afterEach(() => {
  cleanup();
});

describe('VoiceHomeClient startup state', () => {
  it('renders an accessible loading state while runtime configuration is pending', () => {
    mocks.getRuntimeConfig.mockReturnValue(new Promise(() => undefined));

    render(createElement(VoiceHomeClient));

    const status = screen.getByRole('status');
    expect(status.textContent).toContain('正在準備陪伴服務');
    expect(screen.getByRole('main').getAttribute('aria-busy')).toBe('true');
    expect(document.body.textContent?.trim()).not.toBe('');
    expect(mocks.listConsents).not.toHaveBeenCalled();
    expect(mocks.companionPanel).not.toHaveBeenCalled();
    expect(mocks.voicePanel).not.toHaveBeenCalled();
  });

  it('fails closed when runtime configuration rejects unexpectedly', async () => {
    mocks.getRuntimeConfig.mockRejectedValue(new Error('synthetic config failure'));

    render(createElement(VoiceHomeClient));

    await screen.findByText('無法確認登入憑證狀態；系統已停止，不會略過認證');
    expect(screen.getByRole('link', { name: '前往登入 →' }).getAttribute('href')).toBe('/sign-in');
    expect(mocks.listConsents).not.toHaveBeenCalled();
    expect(mocks.companionPanel).not.toHaveBeenCalled();
    expect(mocks.voicePanel).not.toHaveBeenCalled();
  });

  it('fails closed when the BFF credential check is unavailable', async () => {
    mocks.getRuntimeConfig.mockResolvedValue(unavailableConfig);

    render(createElement(VoiceHomeClient));

    await screen.findByText('無法確認登入憑證狀態；系統已停止，不會略過認證');
    expect(screen.getByRole('link', { name: '前往登入 →' }).getAttribute('href')).toBe('/sign-in');
    expect(mocks.listConsents).not.toHaveBeenCalled();
    expect(mocks.companionPanel).not.toHaveBeenCalled();
    expect(mocks.voicePanel).not.toHaveBeenCalled();
  });
});
