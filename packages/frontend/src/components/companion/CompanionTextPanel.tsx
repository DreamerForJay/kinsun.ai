'use client';

import { useState } from 'react';
import { ApiRequestError, type ApiConfig } from '@/lib/api/client';
import { createTextSession, runCompanionTurn, type CompanionTurn } from '@/lib/api/companion';
import { CompanionCharacter } from '@/components/voice/CompanionCharacter';

interface CompanionTextPanelProps {
  apiConfig: ApiConfig;
  elderId: string;
}

function safeErrorMessage(error: unknown): string {
  if (error instanceof ApiRequestError) {
    if (error.status === 404) return '目前無法開始陪伴，請確認身分與長者授權範圍。';
    if (error.status === 409) return '這一輪已結束，請重新送出建立新的一輪。';
    if (error.status === 503) return '陪伴服務暫時沒有回應，您的文字沒有被保存，請稍後再試。';
  }
  return '目前無法完成回覆，您的文字沒有被保存，請稍後再試。';
}

export function CompanionTextPanel({ apiConfig, elderId }: CompanionTextPanelProps) {
  const [inputText, setInputText] = useState('');
  const [submittedText, setSubmittedText] = useState('');
  const [turn, setTurn] = useState<CompanionTurn | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const currentText = inputText.trim();
    if (!currentText || busy) return;

    setBusy(true);
    setError(null);
    setTurn(null);
    try {
      const session = await createTextSession(apiConfig, elderId);
      const result = await runCompanionTurn(apiConfig, session.session_id, currentText);
      setSubmittedText(currentText);
      setTurn(result);
      setInputText('');
    } catch (err) {
      setError(safeErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const message = busy
    ? '我正在整理回答，請稍等一下。'
    : (turn?.reply_text ?? '你好啊！今天想聊什麼呢？');

  return (
    <section
      aria-labelledby="companion-title"
      style={{
        display: 'flex',
        width: 'min(100%, 680px)',
        flexDirection: 'column',
        alignItems: 'stretch',
        gap: 'var(--space-5)',
      }}
    >
      <div style={{ textAlign: 'center' }}>
        <span
          style={{
            display: 'inline-flex',
            padding: 'var(--space-2) var(--space-3)',
            borderRadius: 999,
            background: 'var(--state-review-bg)',
            color: 'var(--state-review-fg)',
            fontSize: 'var(--text-sm)',
          }}
        >
          目前是文字陪伴；麥克風、ASR 與 TTS 尚未啟用
        </span>
      </div>

      <CompanionCharacter
        state={busy ? 'processing' : turn ? 'speaking' : 'idle'}
        message={message}
      />

      <form
        onSubmit={handleSubmit}
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-3)',
          padding: 'var(--space-5)',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-lg)',
          background: 'var(--color-surface)',
        }}
      >
        <label id="companion-title" htmlFor="companion-input" style={{ fontWeight: 700 }}>
          想和小暖說什麼？
        </label>
        <textarea
          id="companion-input"
          value={inputText}
          onChange={(event) => setInputText(event.target.value)}
          maxLength={4000}
          rows={4}
          disabled={busy}
          placeholder="例如：我今天早餐吃了粥。"
          style={{
            width: '100%',
            resize: 'vertical',
            padding: 'var(--space-4)',
            border: '2px solid var(--color-border-strong)',
            borderRadius: 'var(--radius-md)',
            font: 'inherit',
            lineHeight: 'var(--leading-body)',
          }}
        />
        <button
          type="submit"
          disabled={busy || inputText.trim().length === 0}
          style={{
            minHeight: 'var(--touch-min)',
            padding: 'var(--space-3) var(--space-5)',
            border: 0,
            borderRadius: 'var(--radius-md)',
            background: 'var(--color-primary)',
            color: 'var(--color-on-primary)',
            font: 'inherit',
            fontWeight: 700,
            cursor: busy ? 'wait' : 'pointer',
          }}
        >
          {busy ? '正在安全處理…' : '送出文字'}
        </button>
        <small style={{ color: 'var(--color-muted-foreground)' }}>
          文字只用於本輪產生回覆；目前不會寫入長期記憶、照護事件或逐字稿。
        </small>
      </form>

      <div aria-live="polite">
        {submittedText && turn && (
          <p style={{ color: 'var(--color-muted-foreground)' }}>您剛才輸入：「{submittedText}」</p>
        )}
        {turn && turn.safety_decision !== 'ALLOW' && (
          <p
            style={{
              padding: 'var(--space-3)',
              borderRadius: 'var(--radius-md)',
              background: 'var(--state-review-bg)',
              color: 'var(--state-review-fg)',
            }}
          >
            系統已套用安全回覆，沒有把高風險內容當成醫療建議。
          </p>
        )}
        {error && <p style={{ color: 'var(--color-destructive)' }}>{error}</p>}
      </div>
    </section>
  );
}
