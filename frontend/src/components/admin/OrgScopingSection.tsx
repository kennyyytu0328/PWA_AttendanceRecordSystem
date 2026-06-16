"use client";

import { ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { orgScopingApi } from "@/lib/api/org-hierarchy";
import { useTranslation } from "@/lib/i18n";

// ---------------------------------------------------------------------------
// Org-scoping toggle — the master switch for subtree-scoped manager authority.
// ---------------------------------------------------------------------------

export function OrgScopingSection() {
  const { t } = useTranslation();
  const [enabled, setEnabled] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<
    { type: "success" | "error"; text: string } | null
  >(null);

  useEffect(() => {
    let cancelled = false;
    orgScopingApi
      .get()
      .then((data) => {
        if (!cancelled) setEnabled(Boolean(data?.enabled));
      })
      .catch(() => {
        // silent — defaults to off
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
      const result = await orgScopingApi.set(next);
      setEnabled(result.enabled);
      setMessage({ type: "success", text: t("admin.orgScopingSaved") });
    } catch (err) {
      setMessage({
        type: "error",
        text: err instanceof Error ? err.message : t("admin.orgScopingSaveError"),
      });
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <div className="mb-1 flex items-center gap-2">
        <ShieldCheck className="h-5 w-5 text-emerald-600" />
        <h2 className="text-lg font-semibold text-gray-900">
          {t("admin.orgScoping")}
        </h2>
      </div>
      <p className="mb-4 text-xs text-gray-500">{t("admin.orgScopingHint")}</p>

      {isLoading ? (
        <p className="text-sm text-gray-500">{t("common.loading")}</p>
      ) : (
        <>
          <label className="flex cursor-pointer items-center gap-3">
            <button
              type="button"
              role="switch"
              aria-checked={enabled}
              disabled={isSubmitting}
              onClick={() => handleToggle(!enabled)}
              data-testid="org-scoping-toggle"
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors disabled:opacity-50 ${
                enabled ? "bg-emerald-500" : "bg-gray-300"
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  enabled ? "translate-x-6" : "translate-x-1"
                }`}
              />
            </button>
            <span className="text-sm font-medium text-gray-800">
              {enabled ? t("admin.orgScopingOn") : t("admin.orgScopingOff")}
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
