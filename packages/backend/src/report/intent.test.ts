import { describe, expect, it } from 'vitest';
import { detectReportIntent } from './intent.js';

describe('detectReportIntent (A07.3)', () => {
  it('detects a week report request without an explicit range word', () => {
    expect(detectReportIntent('我這禮拜過得如何？')).toBe('week');
    expect(detectReportIntent('可以跟我說一下生活紀錄嗎')).toBe('week');
  });

  it('detects a year report request', () => {
    expect(detectReportIntent('我這一年過得怎麼樣？')).toBe('year');
    expect(detectReportIntent('幫我回顧一下今年的生活狀況')).toBe('year');
  });

  it('does not trigger on an ordinary event statement mentioning a time word', () => {
    expect(detectReportIntent('我這禮拜吃了很多青菜')).toBeNull();
    expect(detectReportIntent('今天天氣真好，我去公園散步了')).toBeNull();
  });

  it('does not trigger on an ordinary medication statement that happens to say 紀錄', () => {
    expect(detectReportIntent('我今天的用藥紀錄是早上八點吃的')).toBeNull();
  });
});
