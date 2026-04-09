"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import en from "@/messages/en.json";
import zh from "@/messages/zh.json";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type Locale = "en" | "zh";

type Messages = typeof en;

const messages: Readonly<Record<Locale, Messages>> = { en, zh };

interface I18nContextType {
  readonly locale: Locale;
  readonly setLocale: (locale: Locale) => void;
  readonly t: (key: string, params?: Record<string, string | number>) => string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const STORAGE_KEY = "app_locale";

function getStoredLocale(): Locale {
  if (typeof window === "undefined") return "en";
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "en" || stored === "zh") return stored;
  // Auto-detect from browser language
  const browserLang = navigator.language.toLowerCase();
  if (browserLang.startsWith("zh")) return "zh";
  return "en";
}

function getNestedValue(obj: unknown, path: string): string | undefined {
  const keys = path.split(".");
  let current: unknown = obj;
  for (const key of keys) {
    if (current === null || current === undefined || typeof current !== "object") {
      return undefined;
    }
    current = (current as Record<string, unknown>)[key];
  }
  return typeof current === "string" ? current : undefined;
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const I18nContext = createContext<I18nContextType | null>(null);

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

interface I18nProviderProps {
  readonly children: ReactNode;
}

export function I18nProvider({ children }: I18nProviderProps) {
  const [locale, setLocaleState] = useState<Locale>("en");

  useEffect(() => {
    setLocaleState(getStoredLocale());
  }, []);

  const setLocale = useCallback((newLocale: Locale) => {
    setLocaleState(newLocale);
    localStorage.setItem(STORAGE_KEY, newLocale);
    document.documentElement.lang = newLocale;
  }, []);

  const t = useCallback(
    (key: string, params?: Record<string, string | number>): string => {
      const value = getNestedValue(messages[locale], key) ?? key;
      if (!params) return value;
      return Object.entries(params).reduce<string>(
        (result, [paramKey, paramValue]) =>
          result.replace(`{${paramKey}}`, String(paramValue)),
        value,
      );
    },
    [locale],
  );

  const value = useMemo<I18nContextType>(
    () => ({ locale, setLocale, t }),
    [locale, setLocale, t],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useTranslation(): I18nContextType {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error("useTranslation must be used within an I18nProvider");
  }
  return context;
}
