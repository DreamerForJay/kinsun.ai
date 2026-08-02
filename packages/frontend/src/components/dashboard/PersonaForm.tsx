'use client';

import { useEffect, useState } from 'react';
import type { PersonaContext } from '@elderly-care/shared';

interface PersonaFormProps {
  persona: PersonaContext | null;
  onSave: (updates: PersonaContext) => Promise<void>;
}

const LANGUAGE_LABELS: Record<PersonaContext['preferredLanguage'], string> = {
  'zh-TW': '中文（國語）',
  'nan-TW': '臺語',
  'hak-TW': '客語',
  'en-US': 'English',
  mixed: '混合',
};

const RESPONSE_LENGTH_LABELS: Record<PersonaContext['responseLength'], string> = {
  short: '簡短',
  medium: '適中',
  long: '詳細',
};

const SPEAKING_SPEED_LABELS: Record<PersonaContext['speakingSpeed'], string> = {
  slow: '慢速',
  normal: '正常',
  fast: '快速',
};

const INTERACTION_STYLE_LABELS: Record<PersonaContext['interactionStyle'], string> = {
  formal: '正式',
  casual: '輕鬆',
  warm: '溫暖親切',
};

export function PersonaForm({ persona, onSave }: PersonaFormProps) {
  const [draft, setDraft] = useState<PersonaContext | null>(persona);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setDraft(persona);
  }, [persona]);

  if (!draft) return <p style={{ color: 'var(--color-muted-foreground)' }}>載入中...</p>;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!draft) return;
    setSaving(true);
    setSaved(false);
    try {
      await onSave(draft);
      setSaved(true);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 480 }}
    >
      <label>
        稱呼
        <input
          type="text"
          value={draft.displayName}
          onChange={(e) => setDraft({ ...draft, displayName: e.target.value })}
          placeholder="例如：阿嬤"
          style={{ display: 'block', width: '100%', padding: 8, marginTop: 4 }}
        />
      </label>

      <label>
        語言偏好
        <select
          value={draft.preferredLanguage}
          onChange={(e) =>
            setDraft({
              ...draft,
              preferredLanguage: e.target.value as PersonaContext['preferredLanguage'],
            })
          }
          style={{ display: 'block', width: '100%', padding: 8, marginTop: 4 }}
        >
          {Object.entries(LANGUAGE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>

      <label>
        回覆長度
        <select
          value={draft.responseLength}
          onChange={(e) =>
            setDraft({
              ...draft,
              responseLength: e.target.value as PersonaContext['responseLength'],
            })
          }
          style={{ display: 'block', width: '100%', padding: 8, marginTop: 4 }}
        >
          {Object.entries(RESPONSE_LENGTH_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>

      <label>
        語速
        <select
          value={draft.speakingSpeed}
          onChange={(e) =>
            setDraft({ ...draft, speakingSpeed: e.target.value as PersonaContext['speakingSpeed'] })
          }
          style={{ display: 'block', width: '100%', padding: 8, marginTop: 4 }}
        >
          {Object.entries(SPEAKING_SPEED_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>

      <label>
        互動風格
        <select
          value={draft.interactionStyle}
          onChange={(e) =>
            setDraft({
              ...draft,
              interactionStyle: e.target.value as PersonaContext['interactionStyle'],
            })
          }
          style={{ display: 'block', width: '100%', padding: 8, marginTop: 4 }}
        >
          {Object.entries(INTERACTION_STYLE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>

      <label>
        自訂問候語
        <textarea
          value={draft.customGreeting}
          onChange={(e) => setDraft({ ...draft, customGreeting: e.target.value })}
          placeholder="例如：早安，今天感覺怎麼樣？"
          rows={3}
          style={{ display: 'block', width: '100%', padding: 8, marginTop: 4 }}
        />
      </label>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <button type="submit" disabled={saving}>
          {saving ? '儲存中...' : '儲存設定'}
        </button>
        {saved && <span style={{ color: 'var(--color-accent-text)', fontSize: 14 }}>已儲存</span>}
      </div>
    </form>
  );
}
