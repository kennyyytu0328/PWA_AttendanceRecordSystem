"use client";

import { useTranslation, type Locale } from "@/lib/i18n";

const LOCALE_LABELS: Readonly<Record<Locale, string>> = {
  en: "EN",
  zh: "中文",
};

export function LanguageSwitcher() {
  const { locale, setLocale } = useTranslation();

  const nextLocale: Locale = locale === "en" ? "zh" : "en";

  return (
    <button
      type="button"
      onClick={() => setLocale(nextLocale)}
      className="fixed right-4 top-4 z-50 flex h-9 items-center justify-center rounded-full bg-white/90 px-3 text-sm font-semibold text-gray-700 shadow-md backdrop-blur-sm transition-colors hover:bg-white hover:text-[#4ec6c1]"
      aria-label={`Switch to ${nextLocale === "zh" ? "Chinese" : "English"}`}
    >
      {LOCALE_LABELS[nextLocale]}
    </button>
  );
}
