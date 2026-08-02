'use client';

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { localeCookieAttributes } from './locale-cookie';
import {
  DEFAULT_LOCALE,
  localeTag,
  translate,
  type Locale,
  type MessageKey,
  type MessageParams,
} from './messages';

interface LocaleContextValue {
  locale: Locale;
  setLocale: (next: Locale) => void;
  t: (key: MessageKey, params?: MessageParams) => string;
  /** Locale-aware date-time for values the Core API returns as ISO strings. */
  formatDateTime: (iso: string | null | undefined) => string;
}

const LocaleContext = createContext<LocaleContextValue | null>(null);

export interface LocaleProviderProps {
  /** Read from the cookie by the (server) layout, so SSR and the first client
   *  render agree — otherwise an `en` visitor gets a flash of Chinese. */
  initialLocale: Locale;
  children: ReactNode;
}

export function LocaleProvider({ initialLocale, children }: LocaleProviderProps) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    if (typeof document !== 'undefined') {
      document.cookie = localeCookieAttributes(next, window.location.protocol === 'https:');
    }
  }, []);

  const value = useMemo<LocaleContextValue>(() => {
    const t = (key: MessageKey, params?: MessageParams) => translate(locale, key, params);
    return {
      locale,
      setLocale,
      t,
      formatDateTime: (iso) =>
        iso ? new Date(iso).toLocaleString(localeTag(locale)) : t('common.empty'),
    };
  }, [locale, setLocale]);

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

/**
 * Throws outside a provider rather than silently defaulting: a care/family
 * component rendered without one would otherwise ignore the switch, and that is
 * far easier to miss in review than a crash on first render.
 */
export function useLocale(): LocaleContextValue {
  const value = useContext(LocaleContext);
  if (!value) {
    throw new Error('useLocale must be used inside a LocaleProvider (care/family surfaces only)');
  }
  return value;
}

export { DEFAULT_LOCALE };
