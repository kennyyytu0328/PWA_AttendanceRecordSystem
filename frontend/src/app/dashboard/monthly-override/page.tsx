"use client";

import { useCallback, useEffect, useState } from "react";
import { Calendar, ChevronLeft, ChevronRight, Save, Send } from "lucide-react";

import { BackButton } from "@/components/BackButton";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { RemarkCell } from "@/components/RemarkCell";
import { WarningModal, type AbnormalDay, type AbnormalStatus } from "@/components/WarningModal";

import { apiClient } from "@/lib/api";
import { deriveDayKindFromWorkday } from "@/lib/day-kind";
import { leaveTypesApi } from "@/lib/api/leave-types";
import {
  monthlySubmissionsApi,
  type SubmissionStatus,
} from "@/lib/api/monthly-submissions";
import { useAuth } from "@/lib/auth-context";
import { useTranslation } from "@/lib/i18n";
import type {
  BulkOverrideEntry,
  BulkOverrideResponse,
  DailyAttendanceSummary,
  DayKind,
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
  readonly day_kind: DayKind;
  readonly clockIn: string;
  readonly clockOut: string;
  readonly status: string;
  readonly isEditable: boolean;
  readonly leaveType: string | null;
  readonly remark: string | null;
  readonly overtimeHours: number | null;
}

const OVERTIME_OPTIONS: readonly number[] = [
  1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 5.5, 6, 6.5, 7, 7.5, 8,
];

const TARDY_STATUSES: ReadonlySet<string> = new Set([
  "LATE",
  "EARLY_LEAVE",
  "LATE_AND_EARLY_LEAVE",
]);

function getRowClass(row: DayRow): string {
  if (row.day_kind === "REGULAR_LEAVE") return "bg-rose-50 text-rose-400";
  if (row.day_kind === "REST_DAY") {
    return row.isEditable
      ? "bg-orange-50/60 hover:bg-orange-50"
      : "bg-orange-50 text-orange-400";
  }
  if (row.is_holiday && !row.is_makeup_workday) return "bg-gray-50 text-gray-400";
  if (TARDY_STATUSES.has(row.status))
    return "bg-red-100 hover:bg-red-200 border-l-4 border-l-red-500 font-medium";
  if (row.is_makeup_workday) return "bg-amber-50/50";
  return "hover:bg-gray-50";
}

const ABNORMAL_STATUSES: ReadonlySet<string> = new Set([
  "LATE",
  "EARLY_LEAVE",
  "LATE_AND_EARLY_LEAVE",
  "ABSENT",
]);

function formatSubmittedAt(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const y = d.getFullYear();
  const mo = String(d.getMonth() + 1).padStart(2, "0");
  const da = String(d.getDate()).padStart(2, "0");
  const h = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  return `${y}-${mo}-${da} ${h}:${mi}`;
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
  switch (day.day_kind) {
    case "MAKEUP_WORKDAY":
      return (
        <span className="inline-block rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-700">
          {t("monthlyOverride.makeupWorkday")}
        </span>
      );
    case "REGULAR_LEAVE":
      return (
        <span className="inline-block rounded-full bg-rose-100 px-2.5 py-0.5 text-xs font-semibold text-rose-700">
          {t("monthlyOverride.regularLeave")}
        </span>
      );
    case "REST_DAY":
      return (
        <span className="inline-block rounded-full bg-orange-100 px-2.5 py-0.5 text-xs font-semibold text-orange-700">
          {t("monthlyOverride.restDay")}
        </span>
      );
    case "NATIONAL_HOLIDAY":
      return (
        <span className="inline-block rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-semibold text-gray-600">
          {day.description || t("monthlyOverride.nationalHoliday")}
        </span>
      );
    case "WORKDAY":
    default:
      return (
        <span className="inline-block rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-semibold text-blue-700">
          {t("monthlyOverride.workday")}
        </span>
      );
  }
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

  // Leave types (fetched once on mount)
  const [leaveTypes, setLeaveTypes] = useState<readonly string[]>([]);

  // Submission status for current (year, month, empId)
  const [submissionStatus, setSubmissionStatus] =
    useState<SubmissionStatus | null>(null);

  // Submit-month flow
  const [warningOpen, setWarningOpen] = useState(false);
  const [pendingSubmit, setPendingSubmit] = useState(false);

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
        const dayKind = deriveDayKindFromWorkday(day);
        // Editability matrix:
        //   REGULAR_LEAVE (Sun) → nobody can edit
        //   REST_DAY (Sat)      → only HR+ can edit
        //   NATIONAL_HOLIDAY    → nobody can edit (unchanged from old behavior)
        //   WORKDAY / MAKEUP_WORKDAY → editable for everyone
        let isEditable: boolean;
        if (dayKind === "REGULAR_LEAVE") {
          isEditable = false;
        } else if (dayKind === "REST_DAY") {
          isEditable = isHrPlus;
        } else if (dayKind === "NATIONAL_HOLIDAY") {
          isEditable = false;
        } else {
          isEditable = true;
        }
        return {
          date: day.date,
          weekday_zh: day.weekday_zh,
          is_holiday: day.is_holiday,
          description: day.description,
          is_makeup_workday: day.is_makeup_workday,
          day_kind: dayKind,
          clockIn: summary ? extractTime(summary.first_clock_in) : "",
          clockOut: summary ? extractTime(summary.last_clock_out) : "",
          status: summary?.status ?? "",
          isEditable,
          leaveType: summary?.leave_type ?? null,
          remark: summary?.remark ?? null,
          overtimeHours:
            summary?.overtime_hours != null ? Number(summary.overtime_hours) : null,
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

  // Resolve which emp_id this page is acting on.
  // For HR+, an empty selection falls back to self so Submit Month / status
  // badge behave the same as Display / Save (which already default to self
  // when no emp_id is sent to the backend).
  const targetEmpId: string | null = isHrPlus
    ? selectedEmpId || user?.emp_id || null
    : user?.emp_id ?? null;

  // Fetch leave types once on mount
  useEffect(() => {
    let cancelled = false;
    async function loadLeaveTypes() {
      try {
        const data = await leaveTypesApi.list();
        if (!cancelled) {
          setLeaveTypes(Array.isArray(data?.leave_types) ? data.leave_types : []);
        }
      } catch {
        // silent — feature still works with empty list
      }
    }
    loadLeaveTypes();
    return () => {
      cancelled = true;
    };
  }, []);

  // Fetch submission status whenever target/year/month changes
  useEffect(() => {
    if (!targetEmpId) {
      setSubmissionStatus(null);
      return;
    }
    let cancelled = false;
    async function loadStatus(empId: string) {
      try {
        const data = await monthlySubmissionsApi.getStatus(empId, year, month);
        if (!cancelled) {
          setSubmissionStatus(data);
        }
      } catch {
        if (!cancelled) {
          setSubmissionStatus(null);
        }
      }
    }
    loadStatus(targetEmpId);
    return () => {
      cancelled = true;
    };
  }, [targetEmpId, year, month]);

  // Handle time input changes. Free-form text input is used (instead of
  // <input type="time">) so the format is locked to 24h HH:MM regardless of
  // the user's OS locale — type="time" follows Windows regional settings
  // and shows AM/PM for en-US users, which is annoying for our Taiwan users.
  // We strip non-digits, auto-insert ":" after 2 digits, cap at 5 chars.
  const normalizeTimeInput = (raw: string): string => {
    const digits = raw.replace(/\D/g, "").slice(0, 4);
    if (digits.length <= 2) return digits;
    return `${digits.slice(0, 2)}:${digits.slice(2)}`;
  };

  const handleClockInChange = useCallback(
    (date: string, value: string) => {
      const normalized = normalizeTimeInput(value);
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
      const normalized = normalizeTimeInput(value);
      setRows((prev) =>
        prev.map((row) =>
          row.date === date ? { ...row, clockOut: normalized } : row,
        ),
      );
    },
    [],
  );

  const handleLeaveTypeChange = useCallback(
    (date: string, value: string | null) => {
      setRows((prev) =>
        prev.map((row) =>
          row.date === date ? { ...row, leaveType: value } : row,
        ),
      );
    },
    [],
  );

  const handleRemarkChange = useCallback((date: string, value: string) => {
    const next = value === "" ? null : value;
    setRows((prev) =>
      prev.map((row) => (row.date === date ? { ...row, remark: next } : row)),
    );
  }, []);

  const handleOvertimeChange = useCallback(
    (date: string, value: string) => {
      const next = value === "" ? null : Number(value);
      setRows((prev) =>
        prev.map((row) =>
          row.date === date ? { ...row, overtimeHours: next } : row,
        ),
      );
    },
    [],
  );

  // Save overrides
  const handleSave = useCallback(async () => {
    const changedEntries: BulkOverrideEntry[] = rows
      .filter((row, idx) => {
        const orig = originalRows[idx];
        return (
          row.isEditable &&
          (row.clockIn !== orig.clockIn ||
            row.clockOut !== orig.clockOut ||
            row.leaveType !== orig.leaveType ||
            row.remark !== orig.remark ||
            row.overtimeHours !== orig.overtimeHours)
        );
      })
      .map((row) => ({
        date: row.date,
        first_clock_in: row.clockIn || null,
        last_clock_out: row.clockOut || null,
        leave_type: row.leaveType,
        remark: row.remark,
        overtime_hours: row.overtimeHours,
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
        entries: readonly BulkOverrideEntry[];
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

  // Build the list of abnormal days for the warning modal
  const abnormalDays: readonly AbnormalDay[] = rows
    .filter((row) => ABNORMAL_STATUSES.has(row.status))
    .map((row) => ({
      date: row.date,
      status: row.status as AbnormalStatus,
      leaveType: row.leaveType,
      remark: row.remark,
    }));

  // Perform the actual submission against the API
  const performSubmit = useCallback(async () => {
    if (!targetEmpId) {
      setMessage({ type: "error", text: t("monthlyOverride.selectEmployeeFirst") });
      return;
    }
    setPendingSubmit(true);
    setMessage(null);
    try {
      await monthlySubmissionsApi.submit(targetEmpId, year, month);
      const status = await monthlySubmissionsApi.getStatus(
        targetEmpId,
        year,
        month,
      );
      setSubmissionStatus(status);
      setMessage({ type: "success", text: t("monthlyOverride.submitSuccess") });
    } catch {
      setMessage({ type: "error", text: t("monthlyOverride.submitError") });
    } finally {
      setPendingSubmit(false);
      setWarningOpen(false);
    }
  }, [targetEmpId, year, month, t]);

  // Click handler for "本月送單" — opens warning modal if abnormal days exist
  const handleSubmitMonth = useCallback(() => {
    if (!targetEmpId) {
      setMessage({ type: "error", text: t("monthlyOverride.selectEmployeeFirst") });
      return;
    }
    if (abnormalDays.length === 0) {
      void performSubmit();
      return;
    }
    setWarningOpen(true);
  }, [targetEmpId, abnormalDays.length, performSubmit, t]);

  const handleWarningProceed = useCallback(() => {
    void performSubmit();
  }, [performSubmit]);

  const handleWarningBack = useCallback(() => {
    setWarningOpen(false);
  }, []);

  const monthLabel = `${year}-${String(month).padStart(2, "0")}`;
  const isSubmitted = submissionStatus?.submitted === true;
  const submittedAtLabel = formatSubmittedAt(submissionStatus?.submitted_at ?? null);

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

          {/* Submission status + Action buttons */}
          <div className="ml-auto flex flex-wrap items-center gap-3">
            {targetEmpId ? (
              isSubmitted ? (
                <span
                  data-testid="submission-status-badge"
                  className="inline-flex items-center gap-1 rounded-full bg-green-100 px-3 py-1 text-xs font-semibold text-green-700"
                  title={submittedAtLabel ? `${t("monthlyOverride.submittedAt")}: ${submittedAtLabel}` : undefined}
                >
                  {t("monthlyOverride.submitted")}
                  {submittedAtLabel ? (
                    <span className="ml-1 font-normal text-green-600">
                      {submittedAtLabel}
                    </span>
                  ) : null}
                </span>
              ) : (
                <span
                  data-testid="submission-status-badge"
                  className="inline-flex items-center rounded-full bg-gray-100 px-3 py-1 text-xs font-semibold text-gray-600"
                >
                  {t("monthlyOverride.notSubmitted")}
                </span>
              )
            ) : null}
            <button
              type="button"
              onClick={handleSubmitMonth}
              disabled={pendingSubmit || !targetEmpId}
              className="inline-flex items-center gap-2 rounded-lg border border-[#4ec6c1] bg-white px-5 py-2 text-sm font-medium text-[#4ec6c1] shadow-sm transition-colors hover:bg-[#e8faf9] disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Send className="h-4 w-4" />
              {pendingSubmit
                ? t("monthlyOverride.submitting")
                : t("monthlyOverride.submitMonth")}
            </button>
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

        {/* Mobile-only scroll hint — hidden once we hit md (table fits) */}
        {!isLoading && (
          <p className="mb-2 text-xs text-gray-500 md:hidden">
            {t("monthlyOverride.scrollHint")}
          </p>
        )}

        {/* 24-hour time format hint — avoids 0530 vs 17:30 mistakes */}
        {!isLoading && (
          <div
            role="note"
            className="mb-3 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800"
          >
            <span aria-hidden="true">⏰</span>
            <span>{t("monthlyOverride.timeFormatHint")}</span>
          </div>
        )}

        {/* Calendar Table */}
        {!isLoading && (
          <div className="overflow-x-auto rounded-xl bg-white shadow-sm">
            <table className="w-full min-w-[720px] text-left text-sm">
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
                    <span className="ml-1 font-normal text-gray-400">(24h)</span>
                  </th>
                  <th className="px-4 py-3 font-medium text-gray-600">
                    {t("monthlyOverride.clockOut")}
                    <span className="ml-1 font-normal text-gray-400">(24h)</span>
                  </th>
                  <th className="px-4 py-3 font-medium text-gray-600">
                    {t("monthlyOverride.leaveType")}
                  </th>
                  <th className="px-4 py-3 font-medium text-gray-600">
                    {t("monthlyOverride.remark")}
                  </th>
                  <th className="px-4 py-3 font-medium text-gray-600">
                    {t("monthlyOverride.overtimeHours")}
                  </th>
                  <th className="px-4 py-3 font-medium text-gray-600">
                    {t("monthlyOverride.status")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const rowClass = getRowClass(row);
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
                          type="text"
                          inputMode="numeric"
                          pattern="([01][0-9]|2[0-3]):[0-5][0-9]"
                          placeholder="HH:MM"
                          maxLength={5}
                          data-testid="clock-in-input"
                          value={row.clockIn}
                          onChange={(e) =>
                            handleClockInChange(row.date, e.target.value)
                          }
                          className="w-20 rounded-lg border border-gray-300 px-2 py-1 text-sm text-gray-900 shadow-sm focus:border-[#4ec6c1] focus:ring-1 focus:ring-[#4ec6c1] focus:outline-none"
                        />
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {row.isEditable ? (
                        <input
                          type="text"
                          inputMode="numeric"
                          pattern="([01][0-9]|2[0-3]):[0-5][0-9]"
                          placeholder="HH:MM"
                          maxLength={5}
                          data-testid="clock-out-input"
                          value={row.clockOut}
                          onChange={(e) =>
                            handleClockOutChange(row.date, e.target.value)
                          }
                          className="w-20 rounded-lg border border-gray-300 px-2 py-1 text-sm text-gray-900 shadow-sm focus:border-[#4ec6c1] focus:ring-1 focus:ring-[#4ec6c1] focus:outline-none"
                        />
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </td>
                    {row.isEditable ? (
                      <td className="px-4 py-3" colSpan={2}>
                        <RemarkCell
                          leaveType={row.leaveType}
                          remark={row.remark}
                          leaveTypes={leaveTypes}
                          onLeaveTypeChange={(v) =>
                            handleLeaveTypeChange(row.date, v)
                          }
                          onRemarkChange={(v) =>
                            handleRemarkChange(row.date, v)
                          }
                        />
                      </td>
                    ) : (
                      <>
                        <td className="px-4 py-3">
                          <span className="text-gray-400">-</span>
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-gray-400">-</span>
                        </td>
                      </>
                    )}
                    <td className="px-4 py-3">
                      {row.isEditable ? (
                        <select
                          data-testid="overtime-select"
                          value={row.overtimeHours ?? ""}
                          onChange={(e) =>
                            handleOvertimeChange(row.date, e.target.value)
                          }
                          className="rounded-lg border border-gray-300 px-2 py-1 text-sm text-gray-900 shadow-sm focus:border-[#4ec6c1] focus:ring-1 focus:ring-[#4ec6c1] focus:outline-none"
                        >
                          <option value="">—</option>
                          {OVERTIME_OPTIONS.map((h) => (
                            <option key={h} value={h}>
                              {h}
                            </option>
                          ))}
                        </select>
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
      <WarningModal
        open={warningOpen}
        abnormalDays={abnormalDays}
        onBackToEdit={handleWarningBack}
        onProceed={handleWarningProceed}
      />
    </div>
  );
}
