"use client";

import { useCallback, useEffect, useState } from "react";
import { Calendar, ChevronLeft, ChevronRight, Save } from "lucide-react";

import { BackButton } from "@/components/BackButton";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";

import { apiClient } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useTranslation } from "@/lib/i18n";
import type {
  BulkOverrideResponse,
  DailyAttendanceSummary,
  Employee,
  Role,
  WorkdayInfo,
  WorkdaysResponse,
} from "@/types";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const HR_ROLES: readonly Role[] = ["HR", "ADMIN"];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function hasRole(role: Role, allowed: readonly Role[]): boolean {
  return allowed.includes(role);
}

function getDaysInMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate();
}

function extractTime(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const h = d.getHours().toString().padStart(2, "0");
  const m = d.getMinutes().toString().padStart(2, "0");
  return `${h}:${m}`;
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface DayRow {
  readonly date: string;
  readonly weekday_zh: string;
  readonly is_holiday: boolean;
  readonly description: string;
  readonly is_makeup_workday: boolean;
  readonly clockIn: string;
  readonly clockOut: string;
  readonly status: string;
  readonly isEditable: boolean;
}

interface Message {
  readonly type: "success" | "error" | "info";
  readonly text: string;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatusBadge({ status, t }: { readonly status: string; readonly t: (key: string) => string }) {
  if (!status) return null;

  const config: Record<string, { color: string; label: string }> = {
    NORMAL: { color: "bg-green-100 text-green-700", label: t("attendance.statusNormal") },
    LATE: { color: "bg-red-100 text-red-700", label: t("attendance.statusLate") },
    EARLY_LEAVE: { color: "bg-amber-100 text-amber-700", label: t("attendance.statusEarlyLeave") },
    LATE_AND_EARLY_LEAVE: { color: "bg-red-100 text-red-700", label: t("attendance.statusLateAndEarlyLeave") },
    ABNORMAL: { color: "bg-gray-100 text-gray-600", label: t("attendance.statusAbnormal") },
  };

  const c = config[status] ?? { color: "bg-gray-100 text-gray-600", label: status };

  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${c.color}`}>
      {c.label}
    </span>
  );
}

function DayTypeBadge({
  day,
  t,
}: {
  readonly day: DayRow;
  readonly t: (key: string) => string;
}) {
  if (day.is_makeup_workday) {
    return (
      <span className="inline-block rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-700">
        {t("monthlyOverride.makeupWorkday")}
      </span>
    );
  }
  if (day.is_holiday) {
    return (
      <span className="inline-block rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-semibold text-gray-600">
        {day.description || t("monthlyOverride.holiday")}
      </span>
    );
  }
  return (
    <span className="inline-block rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-semibold text-blue-700">
      {t("monthlyOverride.workday")}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export default function MonthlyOverridePage() {
  const { user } = useAuth();
  const { t } = useTranslation();
  const role = user?.role ?? "EMPLOYEE";
  const isHrPlus = hasRole(role, HR_ROLES);

  // Month/year state
  const [year, setYear] = useState(() => new Date().getFullYear());
  const [month, setMonth] = useState(() => new Date().getMonth() + 1);

  // Data state
  const [rows, setRows] = useState<readonly DayRow[]>([]);
  const [originalRows, setOriginalRows] = useState<readonly DayRow[]>([]);
  const [employees, setEmployees] = useState<readonly Employee[]>([]);
  const [selectedDepartment, setSelectedDepartment] = useState<string>("");
  const [selectedEmpId, setSelectedEmpId] = useState<string>("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState<Message | null>(null);

  // Derived: unique departments & filtered employees
  const departments = Array.from(
    new Set(employees.map((emp) => emp.department).filter(Boolean)),
  ).sort();
  const filteredEmployees = selectedDepartment
    ? employees.filter((emp) => emp.department === selectedDepartment)
    : employees;

  // Reset employee selection when department changes
  const handleDepartmentChange = useCallback(
    (dept: string) => {
      setSelectedDepartment(dept);
      setSelectedEmpId("");
    },
    [],
  );

  // Navigate months
  const goToPreviousMonth = useCallback(() => {
    setMonth((prev) => {
      if (prev === 1) {
        setYear((y) => y - 1);
        return 12;
      }
      return prev - 1;
    });
    setMessage(null);
  }, []);

  const goToNextMonth = useCallback(() => {
    setMonth((prev) => {
      if (prev === 12) {
        setYear((y) => y + 1);
        return 1;
      }
      return prev + 1;
    });
    setMessage(null);
  }, []);

  // Fetch employees for HR+
  useEffect(() => {
    if (!isHrPlus) return;
    async function loadEmployees() {
      try {
        const data = await apiClient.get<Employee[]>("/api/employees");
        setEmployees(data);
      } catch {
        // silent
      }
    }
    loadEmployees();
  }, [isHrPlus]);

  // Fetch workday calendar + summaries
  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setMessage(null);
    try {
      const startDate = `${year}-${String(month).padStart(2, "0")}-01`;
      const lastDay = getDaysInMonth(year, month);
      const endDate = `${year}-${String(month).padStart(2, "0")}-${String(lastDay).padStart(2, "0")}`;

      const summaryParams = new URLSearchParams({
        start_date: startDate,
        end_date: endDate,
      });
      if (isHrPlus && selectedEmpId) {
        summaryParams.set("emp_id", selectedEmpId);
      }

      const [workdays, summaries] = await Promise.all([
        apiClient.get<WorkdaysResponse>(
          `/api/config/workdays?year=${year}&month=${month}`,
        ),
        apiClient
          .get<DailyAttendanceSummary[]>(
            `/api/attendance/summaries?${summaryParams.toString()}`,
          )
          .catch(() => [] as DailyAttendanceSummary[]),
      ]);

      const summaryMap: Record<string, DailyAttendanceSummary> = {};
      for (const s of summaries) {
        summaryMap[s.date] = s;
      }

      const builtRows: DayRow[] = workdays.days.map((day: WorkdayInfo) => {
        const summary = summaryMap[day.date];
        const isEditable = !day.is_holiday || day.is_makeup_workday;
        return {
          date: day.date,
          weekday_zh: day.weekday_zh,
          is_holiday: day.is_holiday,
          description: day.description,
          is_makeup_workday: day.is_makeup_workday,
          clockIn: summary ? extractTime(summary.first_clock_in) : "",
          clockOut: summary ? extractTime(summary.last_clock_out) : "",
          status: summary?.status ?? "",
          isEditable,
        };
      });

      setRows(builtRows);
      setOriginalRows(builtRows);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to load data";
      setMessage({ type: "error", text: msg });
    } finally {
      setIsLoading(false);
    }
  }, [year, month, isHrPlus, selectedEmpId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Handle time input changes — always normalize to HH:MM (drop seconds)
  const handleClockInChange = useCallback(
    (date: string, value: string) => {
      const normalized = value.slice(0, 5);
      setRows((prev) =>
        prev.map((row) =>
          row.date === date ? { ...row, clockIn: normalized } : row,
        ),
      );
    },
    [],
  );

  const handleClockOutChange = useCallback(
    (date: string, value: string) => {
      const normalized = value.slice(0, 5);
      setRows((prev) =>
        prev.map((row) =>
          row.date === date ? { ...row, clockOut: normalized } : row,
        ),
      );
    },
    [],
  );

  // Save overrides
  const handleSave = useCallback(async () => {
    const changedEntries = rows
      .filter((row, idx) => {
        const orig = originalRows[idx];
        return (
          row.isEditable &&
          (row.clockIn !== orig.clockIn || row.clockOut !== orig.clockOut)
        );
      })
      .map((row) => ({
        date: row.date,
        first_clock_in: row.clockIn || null,
        last_clock_out: row.clockOut || null,
      }));

    if (changedEntries.length === 0) {
      setMessage({ type: "info", text: t("monthlyOverride.noChanges") });
      return;
    }

    setIsSaving(true);
    setMessage(null);
    try {
      const body: {
        year: number;
        month: number;
        entries: typeof changedEntries;
        emp_id?: string;
      } = {
        year,
        month,
        entries: changedEntries,
      };
      if (isHrPlus && selectedEmpId) {
        body.emp_id = selectedEmpId;
      }

      const result = await apiClient.put<BulkOverrideResponse>(
        "/api/attendance/override-bulk",
        body,
      );

      setMessage({
        type: "success",
        text: t("monthlyOverride.saveSuccess").replace(
          "{count}",
          String(result.updated_count),
        ),
      });
      setOriginalRows([...rows]);
    } catch {
      setMessage({ type: "error", text: t("monthlyOverride.saveError") });
    } finally {
      setIsSaving(false);
    }
  }, [rows, originalRows, year, month, isHrPlus, selectedEmpId, t]);

  const monthLabel = `${year}-${String(month).padStart(2, "0")}`;

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#e8faf9] via-[#edfbf0] to-[#f5fbe8] px-4 py-8">
      <LanguageSwitcher />
      <div className="mx-auto max-w-5xl">
        {/* Header */}
        <BackButton className="mb-4" />
        <div className="mb-2 flex items-center gap-3">
          <Calendar className="h-7 w-7 text-[#4ec6c1]" />
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">
            {t("monthlyOverride.title")}
          </h1>
        </div>
        <p className="mb-6 text-sm text-gray-500">
          {t("monthlyOverride.subtitle")}
        </p>

        {/* Controls */}
        <div className="mb-6 flex flex-wrap items-center gap-4 rounded-xl bg-white p-4 shadow-sm">
          {/* Month Navigation */}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={goToPreviousMonth}
              className="rounded-lg border border-gray-300 p-2 text-gray-600 transition-colors hover:bg-gray-100"
              aria-label={t("monthlyOverride.previousMonth")}
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="min-w-[7rem] text-center text-sm font-semibold text-gray-800">
              {monthLabel}
            </span>
            <button
              type="button"
              onClick={goToNextMonth}
              className="rounded-lg border border-gray-300 p-2 text-gray-600 transition-colors hover:bg-gray-100"
              aria-label={t("monthlyOverride.nextMonth")}
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>

          {/* Department & Employee Selector (HR+ only) */}
          {isHrPlus && (
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <label
                  htmlFor="dept-selector"
                  className="text-sm font-medium text-gray-700"
                >
                  {t("monthlyOverride.filterDepartment")}
                </label>
                <select
                  id="dept-selector"
                  value={selectedDepartment}
                  onChange={(e) => handleDepartmentChange(e.target.value)}
                  className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm text-gray-900 shadow-sm focus:border-[#4ec6c1] focus:ring-2 focus:ring-[#4ec6c1] focus:outline-none"
                >
                  <option value="">{t("monthlyOverride.allDepartments")}</option>
                  {departments.map((dept) => (
                    <option key={dept} value={dept}>
                      {dept}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex items-center gap-2">
                <label
                  htmlFor="emp-selector"
                  className="text-sm font-medium text-gray-700"
                >
                  {t("monthlyOverride.selectEmployee")}
                </label>
                <select
                  id="emp-selector"
                  value={selectedEmpId}
                  onChange={(e) => setSelectedEmpId(e.target.value)}
                  className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm text-gray-900 shadow-sm focus:border-[#4ec6c1] focus:ring-2 focus:ring-[#4ec6c1] focus:outline-none"
                >
                  <option value="">--</option>
                  {filteredEmployees.map((emp) => (
                    <option key={emp.emp_id} value={emp.emp_id}>
                      {emp.emp_id} - {emp.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}

          {/* Save Button */}
          <div className="ml-auto">
            <button
              type="button"
              onClick={handleSave}
              disabled={isSaving}
              className="inline-flex items-center gap-2 rounded-lg bg-gradient-to-r from-[#4ec6c1] to-[#6dcf7c] px-5 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:from-[#45b5b0] hover:to-[#5fc06e] disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Save className="h-4 w-4" />
              {isSaving ? t("monthlyOverride.saving") : t("monthlyOverride.save")}
            </button>
          </div>
        </div>

        {/* Message */}
        {message && (
          <div
            role="alert"
            className={`mb-4 rounded-lg border px-4 py-3 text-sm ${
              message.type === "success"
                ? "border-green-200 bg-green-50 text-green-700"
                : message.type === "error"
                  ? "border-red-200 bg-red-50 text-red-700"
                  : "border-blue-200 bg-blue-50 text-blue-700"
            }`}
          >
            {message.text}
          </div>
        )}

        {/* Loading */}
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <div className="text-center">
              <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-4 border-[#4ec6c1]/30 border-t-[#4ec6c1]" />
              <p className="text-sm text-gray-500">{t("common.loading")}</p>
            </div>
          </div>
        )}

        {/* Calendar Table */}
        {!isLoading && (
          <div className="overflow-hidden rounded-xl bg-white shadow-sm">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50">
                  <th className="px-4 py-3 font-medium text-gray-600">
                    {t("monthlyOverride.date")}
                  </th>
                  <th className="px-4 py-3 font-medium text-gray-600">
                    {t("monthlyOverride.day")}
                  </th>
                  <th className="px-4 py-3 font-medium text-gray-600">
                    {t("monthlyOverride.type")}
                  </th>
                  <th className="px-4 py-3 font-medium text-gray-600">
                    {t("monthlyOverride.clockIn")}
                  </th>
                  <th className="px-4 py-3 font-medium text-gray-600">
                    {t("monthlyOverride.clockOut")}
                  </th>
                  <th className="px-4 py-3 font-medium text-gray-600">
                    {t("monthlyOverride.status")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const isTardy =
                    row.status === "LATE" ||
                    row.status === "EARLY_LEAVE" ||
                    row.status === "LATE_AND_EARLY_LEAVE";
                  const rowClass =
                    row.is_holiday && !row.is_makeup_workday
                      ? "bg-gray-50 text-gray-400"
                      : isTardy
                        ? "bg-red-100 hover:bg-red-200 border-l-4 border-l-red-500 font-medium"
                        : row.is_makeup_workday
                          ? "bg-amber-50/50"
                          : "hover:bg-gray-50";
                  return (
                  <tr
                    key={row.date}
                    className={`border-b border-gray-100 last:border-b-0 ${rowClass}`}
                  >
                    <td className="px-4 py-3 text-gray-900">{row.date}</td>
                    <td className="px-4 py-3 text-gray-700">{row.weekday_zh}</td>
                    <td className="px-4 py-3">
                      <DayTypeBadge day={row} t={t} />
                    </td>
                    <td className="px-4 py-3">
                      {row.isEditable ? (
                        <input
                          type="time"
                          step={60}
                          data-testid="clock-in-input"
                          value={row.clockIn}
                          onChange={(e) =>
                            handleClockInChange(row.date, e.target.value)
                          }
                          className="rounded-lg border border-gray-300 px-2 py-1 text-sm text-gray-900 shadow-sm focus:border-[#4ec6c1] focus:ring-1 focus:ring-[#4ec6c1] focus:outline-none"
                        />
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {row.isEditable ? (
                        <input
                          type="time"
                          step={60}
                          data-testid="clock-out-input"
                          value={row.clockOut}
                          onChange={(e) =>
                            handleClockOutChange(row.date, e.target.value)
                          }
                          className="rounded-lg border border-gray-300 px-2 py-1 text-sm text-gray-900 shadow-sm focus:border-[#4ec6c1] focus:ring-1 focus:ring-[#4ec6c1] focus:outline-none"
                        />
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={row.status} t={t} />
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
