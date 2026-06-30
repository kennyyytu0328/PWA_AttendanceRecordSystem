"use client";

import { useCallback, useEffect, useState } from "react";
import { Building, Calendar, Home, Shield, Users } from "lucide-react";

import { BackButton } from "@/components/BackButton";

import { apiClient } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useTranslation } from "@/lib/i18n";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import type { AttendanceLog, Role } from "@/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const MANAGER_ROLES: readonly Role[] = ["MANAGER", "HR", "ADMIN"];

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  const date = d.toLocaleDateString("en-US", {
    month: "2-digit",
    day: "2-digit",
  });
  const time = d.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
  return `${date} ${time}`;
}

function todayString(): string {
  return new Date().toISOString().split("T")[0];
}

function formatDate(iso: string): string {
  return new Date(iso).toISOString().split("T")[0];
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function TeamPage() {
  const { user } = useAuth();
  const { t } = useTranslation();

  const role = user?.role ?? "EMPLOYEE";
  const canAccess = MANAGER_ROLES.includes(role);

  const [logs, setLogs] = useState<readonly AttendanceLog[]>([]);
  const [summaryMap, setSummaryMap] = useState<Readonly<Record<string, { status: string; reason?: string }>>>({});
  // emp_id -> display name, sourced from /api/reports/daily (raw logs carry no
  // name). Lets the table show a recognizable name next to the opaque emp_id.
  const [nameMap, setNameMap] = useState<Readonly<Record<string, string>>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [startDate, setStartDate] = useState(todayString);
  const [endDate, setEndDate] = useState(todayString);

  const fetchLogs = useCallback(
    async (start: string, end: string) => {
      setIsLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams({ start_date: start, end_date: end });
        const endpoint =
          role === "HR" || role === "ADMIN"
            ? `/api/attendance/all?${params.toString()}`
            : `/api/attendance/team?${params.toString()}`;
        const [data, summaries] = await Promise.all([
          apiClient.get<AttendanceLog[]>(endpoint),
          apiClient.get<{ emp_id: string; name?: string; date: string; status: string; reason?: string }[]>(
            `/api/reports/daily?start_date=${start}&end_date=${end}&submission_filter=all`,
          ).catch(() => [] as { emp_id: string; name?: string; date: string; status: string; reason?: string }[]),
        ]);
        setLogs(data);
        const map: Record<string, { status: string; reason?: string }> = {};
        const names: Record<string, string> = {};
        for (const s of summaries) {
          map[`${s.emp_id}_${s.date}`] = { status: s.status, reason: s.reason };
          if (s.name) names[s.emp_id] = s.name;
        }
        setSummaryMap(map);
        setNameMap(names);
      } catch (err) {
        const message =
          err instanceof Error ? err.message : t("team.failedToLoad");
        setError(message);
      } finally {
        setIsLoading(false);
      }
    },
    [role, t],
  );

  useEffect(() => {
    if (canAccess) {
      fetchLogs(startDate, endDate);
    }
  }, [canAccess, fetchLogs, startDate, endDate]);

  if (!canAccess) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-[#e8faf9] via-[#edfbf0] to-[#f5fbe8] px-4 py-8">
        <LanguageSwitcher />
        <div className="mx-auto max-w-4xl">
          <BackButton className="mb-4" />
          <div className="mb-8 flex items-center gap-3">
            <Users className="h-7 w-7 text-[#4ec6c1]" />
            <h1 className="text-2xl font-bold tracking-tight text-gray-900">
              {t("team.title")}
            </h1>
          </div>
          <div className="flex min-h-[400px] items-center justify-center">
            <div className="text-center">
              <Shield className="mx-auto h-12 w-12 text-red-400" />
              <h2 className="mt-4 text-lg font-semibold text-gray-900">
                {t("team.accessDenied")}
              </h2>
              <p className="mt-2 text-sm text-gray-500">
                {t("team.accessDeniedMessage")}
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#e8faf9] via-[#edfbf0] to-[#f5fbe8] px-4 py-8">
      <LanguageSwitcher />
      <div className="mx-auto max-w-4xl">
        {/* Header */}
        <BackButton className="mb-4" />
        <div className="mb-6 flex items-center gap-3">
          <Users className="h-7 w-7 text-[#4ec6c1]" />
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">
            {t("team.title")}
          </h1>
        </div>

        {/* Date Filter */}
        <div className="mb-6 flex flex-wrap items-end gap-4 rounded-xl bg-white p-4 shadow-sm">
          <div className="flex items-center gap-2">
            <Calendar className="h-5 w-5 text-gray-400" />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500">{t("team.startDate")}</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="mt-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm text-gray-900 shadow-sm focus:border-[#4ec6c1] focus:ring-2 focus:ring-[#4ec6c1] focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500">{t("team.endDate")}</label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="mt-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm text-gray-900 shadow-sm focus:border-[#4ec6c1] focus:ring-2 focus:ring-[#4ec6c1] focus:outline-none"
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
              <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-4 border-[#4ec6c1]/30 border-t-[#4ec6c1]" />
              <p className="text-sm text-gray-500">{t("team.loadingRecords")}</p>
            </div>
          </div>
        )}

        {/* Empty State */}
        {!isLoading && !error && logs.length === 0 && (
          <div className="flex flex-col items-center justify-center rounded-xl bg-white py-16 shadow-sm">
            <Users className="mb-3 h-12 w-12 text-gray-300" />
            <p className="text-sm font-medium text-gray-500">
              {t("team.noRecords")}
            </p>
            <p className="mt-1 text-xs text-gray-400">
              {t("team.adjustDate")}
            </p>
          </div>
        )}

        {/* Table */}
        {!isLoading && !error && logs.length > 0 && (
          <div className="overflow-x-auto rounded-xl bg-white shadow-sm">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50">
                  <th className="px-4 py-3 font-medium text-gray-600">{t("team.empId")}</th>
                  <th className="px-4 py-3 font-medium text-gray-600">{t("team.name")}</th>
                  <th className="px-4 py-3 font-medium text-gray-600">{t("team.time")}</th>
                  <th className="px-4 py-3 font-medium text-gray-600">{t("team.workMode")}</th>
                  <th className="px-4 py-3 font-medium text-gray-600">{t("team.location")}</th>
                  <th className="px-4 py-3 font-medium text-gray-600">{t("team.status")}</th>
                  <th className="px-4 py-3 font-medium text-gray-600">{t("team.reason")}</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log, index) => {
                  const empDate = `${log.emp_id}_${formatDate(log.timestamp)}`;
                  const prevKey = index > 0
                    ? `${logs[index - 1].emp_id}_${formatDate(logs[index - 1].timestamp)}`
                    : null;
                  const isFirstOfGroup = empDate !== prevKey;

                  return (
                  <tr
                    key={log.id}
                    className={`border-b border-gray-100 last:border-b-0 hover:bg-gray-50${isFirstOfGroup && index > 0 ? " border-t-2 border-t-gray-300" : ""}`}
                  >
                    <td className="px-4 py-3 font-mono text-xs text-gray-700">{isFirstOfGroup ? log.emp_id : ""}</td>
                    <td className="px-4 py-3 text-gray-700">{isFirstOfGroup ? (nameMap[log.emp_id] ?? "") : ""}</td>
                    <td className="px-4 py-3 text-gray-700">{formatDateTime(log.timestamp)}</td>
                    <td className="px-4 py-3">
                      <WorkModeBadge mode={log.work_mode} />
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-500">
                      {log.latitude.toFixed(4)}, {log.longitude.toFixed(4)}
                    </td>
                    <td className="px-4 py-3">
                      {isFirstOfGroup && <StatusBadge status={summaryMap[empDate]?.status} />}
                      {log.is_overridden && (
                        <span className="ml-1 inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
                          {t("team.overridden")}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-600">
                      {isFirstOfGroup && summaryMap[empDate]?.reason
                        ? summaryMap[empDate].reason
                        : null}
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

function WorkModeBadge({ mode }: { readonly mode: "OFFICE" | "WFH" }) {
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
