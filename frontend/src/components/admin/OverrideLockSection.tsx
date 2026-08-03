"use client";

import { Lock } from "lucide-react";
import { useEffect, useState } from "react";

import { overrideLockApi } from "@/lib/api/override-lock";
import { useTranslation } from "@/lib/i18n";

// ---------------------------------------------------------------------------
// Override-lock toggle — HR month-end switch that freezes monthly punch
// override editing for EMPLOYEE/MANAGER while HR/ADMIN stay unaffected.
// ---------------------------------------------------------------------------

export function OverrideLockSection() {
  const { t } = useTranslation();
  const [locked, setLocked] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<
    { type: "success" | "error"; text: string } | null
  >(null);

  useEffect(() => {
    let cancelled = false;
    overrideLockApi
      .get()
      .then((data) => {
        if (!cancelled) setLocked(Boolean(data?.locked));
      })
      .catch(() => {
        // silent — defaults to unlocked
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleToggle(next: boolean) {
    setIsSubmitting(true);
    setMessage(null);
    try {
      const result = await overrideLockApi.set(next);
      setLocked(result.locked);
      setMessage({ type: "success", text: t("admin.overrideLockSaved") });
    } catch (err) {
      setMessage({
        type: "error",
        text: err instanceof Error ? err.message : t("admin.overrideLockSaveError"),
      });
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <div className="mb-1 flex items-center gap-2">
        <Lock className="h-5 w-5 text-red-600" />
        <h2 className="text-lg font-semibold text-gray-900">
          {t("admin.overrideLock")}
        </h2>
      </div>
      <p className="mb-4 text-xs text-gray-500">{t("admin.overrideLockHint")}</p>

      {isLoading ? (
        <p className="text-sm text-gray-500">{t("common.loading")}</p>
      ) : (
        <>
          <label className="flex cursor-pointer items-center gap-3">
            <button
              type="button"
              role="switch"
              aria-checked={locked}
              disabled={isSubmitting}
              onClick={() => handleToggle(!locked)}
              data-testid="override-lock-toggle"
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors disabled:opacity-50 ${
                locked ? "bg-red-500" : "bg-gray-300"
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  locked ? "translate-x-6" : "translate-x-1"
                }`}
              />
            </button>
            <span className="text-sm font-medium text-gray-800">
              {locked ? t("admin.overrideLockOn") : t("admin.overrideLockOff")}
            </span>
          </label>

          {message && (
            <div
              className={`mt-3 rounded-lg border px-3 py-2 text-sm ${
                message.type === "success"
                  ? "border-green-200 bg-green-50 text-green-700"
                  : "border-red-200 bg-red-50 text-red-700"
              }`}
            >
              {message.text}
            </div>
          )}
        </>
      )}
    </section>
  );
}
