import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

import en from "@/messages/en.json";

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

function translate(key: string, params?: Record<string, string | number>): string {
  const value = getNestedValue(en, key) ?? key;
  if (!params) return value;
  return Object.entries(params).reduce<string>(
    (result, [paramKey, paramValue]) =>
      result.replace(`{${paramKey}}`, String(paramValue)),
    value,
  );
}

vi.mock("@/lib/i18n", async () => {
  const { createElement } = await import("react");
  return {
    useTranslation: () => ({
      locale: "en" as const,
      setLocale: vi.fn(),
      t: translate,
    }),
    I18nProvider: ({ children }: { children: React.ReactNode }) =>
      createElement("div", null, children),
  };
});

vi.mock("@/components/LanguageSwitcher", () => ({
  LanguageSwitcher: () => null,
}));
