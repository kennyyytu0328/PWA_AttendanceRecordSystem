"use client";

import { ArrowDown, ArrowUp, Network, Plus, X } from "lucide-react";
import { useEffect, useState } from "react";

import { ranksApi } from "@/lib/api/org-hierarchy";
import { useTranslation } from "@/lib/i18n";

// ---------------------------------------------------------------------------
// Org-chart Ranks Management (ordered, most-senior first)
// ---------------------------------------------------------------------------

export function RanksTab() {
  const { t } = useTranslation();
  const [ranks, setRanks] = useState<readonly string[]>([]);
  const [newRank, setNewRank] = useState("");
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
        const data = await ranksApi.list();
        if (!cancelled) {
          setRanks(Array.isArray(data?.ranks) ? data.ranks : []);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : t("admin.ranksLoadError"));
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [t]);

  function handleAdd() {
    const trimmed = newRank.trim();
    if (!trimmed) return;
    if (ranks.includes(trimmed)) {
      setMessage({ type: "error", text: t("admin.ranksDuplicate") });
      return;
    }
    setRanks((prev) => [...prev, trimmed]);
    setNewRank("");
    setMessage(null);
  }

  function handleRemove(rank: string) {
    setRanks((prev) => prev.filter((r) => r !== rank));
    setMessage(null);
  }

  function move(index: number, delta: number) {
    setRanks((prev) => {
      const next = [...prev];
      const target = index + delta;
      if (target < 0 || target >= next.length) return prev;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
    setMessage(null);
  }

  async function handleSave() {
    setIsSubmitting(true);
    setMessage(null);
    try {
      const result = await ranksApi.update([...ranks]);
      setRanks(result.ranks);
      setMessage({ type: "success", text: t("admin.ranksSaved") });
    } catch (err) {
      setMessage({
        type: "error",
        text: err instanceof Error ? err.message : t("admin.ranksSaveError"),
      });
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <div className="mb-1 flex items-center gap-2">
        <Network className="h-5 w-5 text-indigo-600" />
        <h2 className="text-lg font-semibold text-gray-900">{t("admin.ranks")}</h2>
      </div>
      <p className="mb-4 text-xs text-gray-500">{t("admin.ranksHint")}</p>

      {isLoading && <p className="text-sm text-gray-500">{t("common.loading")}</p>}

      {error && (
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {!isLoading && !error && (
        <>
          {ranks.length === 0 && (
            <p className="mb-4 text-sm text-gray-500">{t("admin.ranksEmpty")}</p>
          )}

          {ranks.length > 0 && (
            <ol className="mb-4 space-y-2">
              {ranks.map((rank, index) => (
                <li
                  key={rank}
                  className="flex items-center gap-2 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-sm text-indigo-900"
                >
                  <span className="w-5 text-xs text-indigo-400">{index + 1}</span>
                  <span className="flex-1 font-medium">{rank}</span>
                  <button
                    type="button"
                    onClick={() => move(index, -1)}
                    disabled={isSubmitting || index === 0}
                    aria-label={`${t("admin.ranksMoveUp")} ${rank}`}
                    className="rounded p-0.5 text-indigo-400 hover:bg-indigo-200 hover:text-indigo-700 disabled:opacity-30"
                  >
                    <ArrowUp className="h-3.5 w-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => move(index, 1)}
                    disabled={isSubmitting || index === ranks.length - 1}
                    aria-label={`${t("admin.ranksMoveDown")} ${rank}`}
                    className="rounded p-0.5 text-indigo-400 hover:bg-indigo-200 hover:text-indigo-700 disabled:opacity-30"
                  >
                    <ArrowDown className="h-3.5 w-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => handleRemove(rank)}
                    disabled={isSubmitting}
                    data-testid={`ranks-remove-${rank}`}
                    aria-label={`${t("admin.ranksRemove")} ${rank}`}
                    className="rounded-full p-0.5 text-indigo-400 hover:bg-indigo-200 hover:text-indigo-700 disabled:opacity-50"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </li>
              ))}
            </ol>
          )}

          <div className="mb-4 flex items-center gap-2">
            <input
              type="text"
              value={newRank}
              onChange={(e) => setNewRank(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  handleAdd();
                }
              }}
              placeholder={t("admin.ranksPlaceholder")}
              className="flex-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm shadow-sm focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
            />
            <button
              type="button"
              onClick={handleAdd}
              disabled={isSubmitting || !newRank.trim()}
              data-testid="ranks-add-button"
              className="flex items-center gap-1 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Plus className="h-3.5 w-3.5" />
              {t("admin.ranksAdd")}
            </button>
          </div>

          <button
            type="button"
            onClick={handleSave}
            disabled={isSubmitting}
            data-testid="ranks-save-button"
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
