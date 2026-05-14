"use client";

import { Plus, Tag, X } from "lucide-react";
import { useEffect, useState } from "react";

import { leaveTypesApi } from "@/lib/api/leave-types";
import { useTranslation } from "@/lib/i18n";

// ---------------------------------------------------------------------------
// Leave Types Management Section
// ---------------------------------------------------------------------------

export function LeaveTypesTab() {
  const { t } = useTranslation();
  const [leaveTypes, setLeaveTypes] = useState<readonly string[]>([]);
  const [newType, setNewType] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<
    { type: "success" | "error"; text: string } | null
  >(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const data = await leaveTypesApi.list();
        if (!cancelled) {
          setLeaveTypes(Array.isArray(data?.leave_types) ? data.leave_types : []);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          const msg =
            err instanceof Error ? err.message : t("admin.leaveTypesLoadError");
          setError(msg);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [t]);

  function handleAdd() {
    const trimmed = newType.trim();
    if (!trimmed) return;
    let duplicate = false;
    setLeaveTypes((prev) => {
      if (prev.includes(trimmed)) {
        duplicate = true;
        return prev;
      }
      return [...prev, trimmed];
    });
    if (duplicate) {
      setMessage({ type: "error", text: t("admin.leaveTypesDuplicate") });
      return;
    }
    setNewType("");
    setMessage(null);
  }

  function handleRemove(type: string) {
    setLeaveTypes((prev) => prev.filter((lt) => lt !== type));
    setMessage(null);
  }

  async function handleSave() {
    setIsSubmitting(true);
    setMessage(null);
    try {
      const result = await leaveTypesApi.update([...leaveTypes]);
      setLeaveTypes(result.leave_types);
      setMessage({ type: "success", text: t("admin.leaveTypesSaved") });
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : t("admin.leaveTypesSaveError");
      setMessage({ type: "error", text: msg });
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex items-center gap-2">
        <Tag className="h-5 w-5 text-rose-600" />
        <h2 className="text-lg font-semibold text-gray-900">
          {t("admin.leaveTypes")}
        </h2>
      </div>

      {isLoading && (
        <p className="text-sm text-gray-500">{t("common.loading")}</p>
      )}

      {error && (
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
        >
          {error}
        </div>
      )}

      {!isLoading && !error && (
        <>
          {leaveTypes.length === 0 && (
            <p className="mb-4 text-sm text-gray-500">
              {t("admin.leaveTypesEmpty")}
            </p>
          )}

          {leaveTypes.length > 0 && (
            <ul className="mb-4 flex flex-wrap gap-2">
              {leaveTypes.map((type) => (
                <li
                  key={type}
                  className="inline-flex items-center gap-1.5 rounded-full border border-rose-200 bg-rose-50 py-1 pr-1 pl-3 text-sm text-rose-800"
                >
                  <span>{type}</span>
                  <button
                    type="button"
                    onClick={() => handleRemove(type)}
                    disabled={isSubmitting}
                    data-testid={`leave-types-remove-${type}`}
                    className="rounded-full p-0.5 text-rose-400 transition-colors hover:bg-rose-200 hover:text-rose-700 disabled:opacity-50"
                    title={t("admin.leaveTypesRemove")}
                    aria-label={`${t("admin.leaveTypesRemove")} ${type}`}
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          )}

          <div className="mb-4 flex items-center gap-2">
            <input
              type="text"
              value={newType}
              onChange={(e) => setNewType(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  handleAdd();
                }
              }}
              placeholder={t("admin.leaveTypesPlaceholder")}
              className="flex-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm shadow-sm focus:border-rose-500 focus:ring-2 focus:ring-rose-500 focus:outline-none"
            />
            <button
              type="button"
              onClick={handleAdd}
              disabled={isSubmitting || !newType.trim()}
              data-testid="leave-types-add-button"
              className="flex items-center gap-1 rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-rose-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Plus className="h-3.5 w-3.5" />
              {t("admin.leaveTypesAdd")}
            </button>
          </div>

          <button
            type="button"
            onClick={handleSave}
            disabled={isSubmitting}
            data-testid="leave-types-save-button"
            className="rounded-lg bg-gradient-to-r from-[#4ec6c1] to-[#6dcf7c] px-4 py-2 text-sm font-semibold text-white shadow-sm hover:from-[#45b5b0] hover:to-[#5fc06e] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSubmitting ? t("common.saving") : t("common.save")}
          </button>

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
