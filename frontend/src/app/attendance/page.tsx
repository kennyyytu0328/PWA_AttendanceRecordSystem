"use client";

import { useCallback, useEffect, useState } from "react";
import { Building, Calendar, History, Home } from "lucide-react";

import { BackButton } from "@/components/BackButton";

import { apiClient } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useTranslation } from "@/lib/i18n";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import type { AttendanceLog, DailyAttendanceSummary } from "@/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toISOString().split("T")[0];
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}

function buildQueryPath(startDate: string, endDate: string): string {
  const params = new URLSearchParams();
  if (startDate) {
    params.set("start_date", startDate);
  }
  if (endDate) {
    params.set("end_date", endDate);
  }
  const qs = params.toString();
  return qs ? `/api/attendance?${qs}` : "/api/attendance";
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function AttendancePage() {
  const { user } = useAuth();
  const { t } = useTranslation();

  const [logs, setLogs] = useState<readonly AttendanceLog[]>([]);
  const [summaryMap, setSummaryMap] = useState<Readonly<Record<string, string>>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [startDate, setStartDate] = useState(() => {
    const now = new Date();
    const day = now.getDay();
    const monday = new Date(now);
    monday.setDate(now.getDate() - (day === 0 ? 6 : day - 1));
    return monday.toISOString().split("T")[0];
  });
  const [endDate, setEndDate] = useState(() => {
    const now = new Date();
    const day = now.getDay();
    const sunday = new Date(now);
    sunday.setDate(now.getDate() + (day === 0 ? 0 : 7 - day));
    return sunday.toISOString().split("T")[0];
  });

  const fetchLogs = useCallback(async (start: string, end: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const path = buildQueryPath(start, end);
      const [data, summaries] = await Promise.all([
        apiClient.get<AttendanceLog[]>(path),
        apiClient.get<{ date: string; status: string }[]>(
          `/api/attendance/summaries?start_date=${start}&end_date=${end}`,
        ).catch(() => [] as { date: string; status: string }[]),
      ]);
      setLogs(data);
      const map: Record<string, string> = {};
      for (const s of summaries) {
        map[s.date] = s.status;
      }
      setSummaryMap(map);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : t("attendance.failedToLoad");
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  useEffect(() => {
    fetchLogs(startDate, endDate);
  }, [fetchLogs, startDate, endDate]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#e8faf9] via-[#edfbf0] to-[#f5fbe8] px-4 py-8">
      <LanguageSwitcher />
      <div className="mx-auto max-w-4xl">
        {/* Header */}
        <BackButton className="mb-4" />
        <div className="mb-6 flex items-center gap-3">
          <History className="h-7 w-7 text-[#4ec6c1]" />
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">
            {t("attendance.title")}
          </h1>
        </div>

        {/* Date Filters */}
        <div className="mb-6 flex flex-wrap items-end gap-4 rounded-xl bg-white p-4 shadow-sm">
          <div className="flex items-center gap-2">
            <Calendar className="h-5 w-5 text-gray-400" />
            <span className="text-sm font-medium text-gray-700">{t("attendance.filterByDate")}</span>
          </div>
          <div>
            <label
              htmlFor="start-date"
              className="block text-xs font-medium text-gray-500"
            >
              {t("attendance.startDate")}
            </label>
            <input
              id="start-date"
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="mt-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-500 focus:outline-none"
            />
          </div>
          <div>
            <label
              htmlFor="end-date"
              className="block text-xs font-medium text-gray-500"
            >
              {t("attendance.endDate")}
            </label>
            <input
              id="end-date"
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="mt-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-500 focus:outline-none"
            />
          </div>
        </div>

        {/* Error */}
        {error && (
          <div
            role="alert"
            className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
          >
            {error}
          </div>
        )}

        {/* Loading */}
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <div className="text-center">
              <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-4 border-blue-200 border-t-blue-600" />
              <p className="text-sm text-gray-500">{t("attendance.loadingRecords")}</p>
            </div>
          </div>
        )}

        {/* Empty State */}
        {!isLoading && !error && logs.length === 0 && (
          <div className="flex flex-col items-center justify-center rounded-xl bg-white py-16 shadow-sm">
            <History className="mb-3 h-12 w-12 text-gray-300" />
            <p className="text-sm font-medium text-gray-500">
              {t("attendance.noRecords")}
            </p>
            <p className="mt-1 text-xs text-gray-400">
              {t("attendance.adjustFilters")}
            </p>
          </div>
        )}

        {/* Table */}
        {!isLoading && !error && logs.length > 0 && (
          <div className="overflow-hidden rounded-xl bg-white shadow-sm">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50">
                  <th className="px-4 py-3 font-medium text-gray-600">{t("attendance.date")}</th>
                  <th className="px-4 py-3 font-medium text-gray-600">{t("attendance.time")}</th>
                  <th className="px-4 py-3 font-medium text-gray-600">{t("attendance.workMode")}</th>
                  <th className="px-4 py-3 font-medium text-gray-600">{t("attendance.location")}</th>
                  <th className="px-4 py-3 font-medium text-gray-600">{t("attendance.status")}</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log, index) => {
                  const date = formatDate(log.timestamp);
                  const prevDate = index > 0 ? formatDate(logs[index - 1].timestamp) : null;
                  const isFirstOfDate = date !== prevDate;

                  return (
                  <tr
                    key={log.id}
                    className={`border-b border-gray-100 last:border-b-0 hover:bg-gray-50${isFirstOfDate && index > 0 ? " border-t-2 border-t-gray-300" : ""}`}
                  >
                    <td className="px-4 py-3 text-gray-900">
                      {isFirstOfDate ? date : ""}
                    </td>
                    <td className="px-4 py-3 text-gray-700">
                      {formatTime(log.timestamp)}
                    </td>
                    <td className="px-4 py-3">
                      <WorkModeBadge mode={log.work_mode} />
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-500">
                      {log.latitude.toFixed(4)}, {log.longitude.toFixed(4)}
                    </td>
                    <td className="px-4 py-3">
                      {isFirstOfDate && <StatusBadge status={summaryMap[date]} />}
                      {log.is_overridden && (
                        <span className="ml-1 inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
                          {t("attendance.overridden")}
                        </span>
                      )}
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface WorkModeBadgeProps {
  readonly mode: "OFFICE" | "WFH";
}

function StatusBadge({ status }: { readonly status: string | undefined }) {
  const { t } = useTranslation();

  if (!status) return null;

  const config: Record<string, { color: string; label: string }> = {
    NORMAL: { color: "bg-green-100 text-green-700", label: t("attendance.statusNormal") },
    LATE: { color: "bg-red-100 text-red-700", label: t("attendance.statusLate") },
    EARLY_LEAVE: { color: "bg-amber-100 text-amber-700", label: t("attendance.statusEarlyLeave") },
    LATE_AND_EARLY_LEAVE: { color: "bg-red-100 text-red-700", label: t("attendance.statusLateAndEarlyLeave") },
    ABNORMAL: { color: "bg-gray-100 text-gray-600", label: t("attendance.statusAbnormal") },
    ABSENT: { color: "bg-red-100 text-red-700", label: t("attendance.statusAbsent") },
  };

  const c = config[status] ?? { color: "bg-gray-100 text-gray-600", label: status };

  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${c.color}`}>
      {c.label}
    </span>
  );
}

function WorkModeBadge({ mode }: WorkModeBadgeProps) {
  const { t } = useTranslation();

  if (mode === "OFFICE") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-semibold text-blue-700">
        <Building className="h-3 w-3" />
        {t("attendance.wfo")}
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-semibold text-green-700">
      <Home className="h-3 w-3" />
      {t("attendance.wfh")}
    </span>
  );
}
