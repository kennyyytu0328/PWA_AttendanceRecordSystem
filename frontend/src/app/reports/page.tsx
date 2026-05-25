"use client";

import { useCallback, useEffect, useState } from "react";
import { Calendar, Download, FileText, RefreshCw, Shield } from "lucide-react";

import { BackButton } from "@/components/BackButton";

import { apiClient } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { buildExportFilename } from "@/lib/exportFilename";
import { useTranslation } from "@/lib/i18n";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import type { DailyAttendanceSummary, Employee, Role, SubmissionFilter } from "@/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const MANAGER_ROLES: readonly Role[] = ["MANAGER", "HR", "ADMIN"];
const HR_ROLES: readonly Role[] = ["HR", "ADMIN"];

function todayString(): string {
  return new Date().toISOString().split("T")[0];
}

function truncate(value: string | null | undefined, max = 50): string {
  if (!value) return "-";
  return value.length > max ? `${value.slice(0, max)}…` : value;
}

function SubmissionBadge({ status, label }: { readonly status: string; readonly label: string }) {
  const cls =
    status === "submitted"
      ? "bg-green-100 text-green-700"
      : "bg-gray-100 text-gray-600";
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${cls}`}>
      {label}
    </span>
  );
}

function formatTime(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  return d.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}

/**
 * First-In-Last-Out collapses a single physical punch to first === last. The
 * echoed clock-out isn't a real clock-out ("clocked in, never clocked out"),
 * so it should display as "no record" rather than the same time twice.
 */
function isSinglePunch(
  firstClockIn: string | null,
  lastClockOut: string | null,
): boolean {
  return firstClockIn != null && firstClockIn === lastClockOut;
}

// ---------------------------------------------------------------------------
// Status Badge
// ---------------------------------------------------------------------------

function StatusBadge({ status, label }: { readonly status: string; readonly label: string }) {
  const colors: Record<string, string> = {
    NORMAL: "bg-green-100 text-green-700",
    LATE: "bg-red-100 text-red-700",
    EARLY_LEAVE: "bg-amber-100 text-amber-700",
    LATE_AND_EARLY_LEAVE: "bg-red-100 text-red-700",
    ABNORMAL: "bg-gray-100 text-gray-600",
    ABSENT: "bg-red-100 text-red-700",
    LEAVE: "bg-blue-100 text-blue-700",
  };

  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${colors[status] ?? "bg-gray-100 text-gray-600"}`}>
      {label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Daily Report Section
// ---------------------------------------------------------------------------

function DailyReportSection({ isHr }: { readonly isHr: boolean }) {
  const { t } = useTranslation();
  const [startDate, setStartDate] = useState(todayString);
  const [endDate, setEndDate] = useState(todayString);
  const [department, setDepartment] = useState("");
  const [selectedEmployee, setSelectedEmployee] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [submissionFilter, setSubmissionFilter] = useState<SubmissionFilter>("all");
  const [showTerminated, setShowTerminated] = useState(false);
  const [data, setData] = useState<readonly DailyAttendanceSummary[]>([]);
  const [departments, setDepartments] = useState<readonly string[]>([]);
  const [employees, setEmployees] = useState<readonly Employee[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchEmployeesAndDepts() {
      try {
        const qs = isHr && showTerminated ? "?include_terminated=true" : "";
        const emps = await apiClient.get<Employee[]>(`/api/employees${qs}`);
        setEmployees(emps);
        const depts = [...new Set(emps.map((e) => e.department))].sort();
        setDepartments(depts);
      } catch {
        // silent — dropdown will just show "all"
      }
    }
    fetchEmployeesAndDepts();
  }, [isHr, showTerminated]);

  // Clear stale employee/department selections when they disappear from the
  // dropdown (e.g., HR unticks "Include resigned employees" while a resigned
  // employee is selected). Without this, the state still carries the emp_id
  // and the backend honors the explicit filter (LSA priority) — showing stale
  // results after the dropdown visually reset to "All".
  useEffect(() => {
    if (selectedEmployee && !employees.some((e) => e.emp_id === selectedEmployee)) {
      setSelectedEmployee("");
    }
    if (department && !employees.some((e) => e.department === department)) {
      setDepartment("");
    }
  }, [employees, selectedEmployee, department]);

  const statusLabelMap: Record<string, string> = {
    NORMAL: t("reports.statusOnTime"),
    LATE: t("reports.statusLate"),
    EARLY_LEAVE: t("reports.statusEarlyLeave"),
    LATE_AND_EARLY_LEAVE: t("reports.statusLateAndEarlyLeave"),
    ABNORMAL: t("reports.statusAbnormal"),
    ABSENT: t("reports.statusAbsent"),
    LEAVE: t("status.leave"),
  };

  const fetchReport = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ start_date: startDate, end_date: endDate });
      if (department) params.set("department", department);
      if (selectedEmployee) params.set("emp_id", selectedEmployee);
      if (statusFilter) params.set("status", statusFilter);
      if (isHr) params.set("submission_filter", submissionFilter);
      if (isHr && showTerminated) params.set("include_terminated", "true");

      const result = await apiClient.get<DailyAttendanceSummary[]>(
        `/api/reports/daily?${params.toString()}`,
      );
      setData(result);
    } catch (err) {
      const message = err instanceof Error ? err.message : t("reports.failedToLoad");
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, [startDate, endDate, department, selectedEmployee, statusFilter, submissionFilter, isHr, showTerminated, t]);

  useEffect(() => {
    fetchReport();
  }, [fetchReport]);

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold text-gray-900">
        <Calendar className="h-5 w-5 text-[#4ec6c1]" />
        {t("reports.dailyReport")}
      </h2>

      {/* Filters */}
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div>
          <label className="block text-xs font-medium text-gray-500">{t("reports.startDate")}</label>
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="mt-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm shadow-sm focus:border-[#4ec6c1] focus:ring-2 focus:ring-[#4ec6c1] focus:outline-none"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-500">{t("reports.endDate")}</label>
          <input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="mt-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm shadow-sm focus:border-[#4ec6c1] focus:ring-2 focus:ring-[#4ec6c1] focus:outline-none"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-500">{t("reports.department")}</label>
          <select
            value={department}
            onChange={(e) => setDepartment(e.target.value)}
            className="mt-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm shadow-sm focus:border-[#4ec6c1] focus:ring-2 focus:ring-[#4ec6c1] focus:outline-none"
          >
            <option value="">{t("reports.departmentPlaceholder")}</option>
            {departments.map((dept) => (
              <option key={dept} value={dept}>{dept}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-500">{t("reports.employee")}</label>
          <select
            value={selectedEmployee}
            onChange={(e) => setSelectedEmployee(e.target.value)}
            className="mt-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm shadow-sm focus:border-[#4ec6c1] focus:ring-2 focus:ring-[#4ec6c1] focus:outline-none"
          >
            <option value="">{t("reports.employeePlaceholder")}</option>
            {employees.map((emp) => (
              <option key={emp.emp_id} value={emp.emp_id}>
                {emp.emp_id} - {emp.name}
                {emp.terminated_at ? ` ${t("reports.terminatedOption")}` : ""}
              </option>
            ))}
          </select>
        </div>
        {isHr && (
          <div>
            <label className="block text-xs font-medium text-gray-500">&nbsp;</label>
            <label className="mt-1 flex cursor-pointer items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs text-gray-600 shadow-sm">
              <input
                type="checkbox"
                checked={showTerminated}
                onChange={(e) => setShowTerminated(e.target.checked)}
                className="h-3.5 w-3.5 rounded border-gray-300 text-[#4ec6c1] focus:ring-[#4ec6c1]"
              />
              {showTerminated ? t("reports.hideTerminated") : t("reports.showTerminated")}
            </label>
          </div>
        )}
        <div>
          <label className="block text-xs font-medium text-gray-500">{t("reports.statusFilter")}</label>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="mt-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm shadow-sm focus:border-[#4ec6c1] focus:ring-2 focus:ring-[#4ec6c1] focus:outline-none"
          >
            <option value="">{t("reports.statusAll")}</option>
            <option value="NORMAL">{t("reports.statusOnTime")}</option>
            <option value="LATE">{t("reports.statusLate")}</option>
            <option value="EARLY_LEAVE">{t("reports.statusEarlyLeave")}</option>
            <option value="LATE_AND_EARLY_LEAVE">{t("reports.statusLateAndEarlyLeave")}</option>
            <option value="ABNORMAL">{t("reports.statusAbnormal")}</option>
            <option value="ABSENT">{t("reports.statusAbsent")}</option>
          </select>
        </div>
        {isHr && (
          <div>
            <label className="block text-xs font-medium text-gray-500">{t("reports.submissionFilter")}</label>
            <select
              value={submissionFilter}
              onChange={(e) => setSubmissionFilter(e.target.value as SubmissionFilter)}
              className="mt-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm shadow-sm focus:border-[#4ec6c1] focus:ring-2 focus:ring-[#4ec6c1] focus:outline-none"
              aria-label={t("reports.submissionFilter")}
            >
              <option value="all">{t("reports.filterAll")}</option>
              <option value="submitted">{t("reports.filterSubmitted")}</option>
              <option value="unsubmitted">{t("reports.filterUnsubmitted")}</option>
            </select>
          </div>
        )}
      </div>

      {/* Error */}
      {error && (
        <div role="alert" className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-8">
          <div className="text-center">
            <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-4 border-[#4ec6c1]/30 border-t-[#4ec6c1]" />
            <p className="text-sm text-gray-500">{t("reports.loadingReport")}</p>
          </div>
        </div>
      )}

      {/* Empty */}
      {!isLoading && !error && data.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12">
          <FileText className="mb-3 h-10 w-10 text-gray-300" />
          <p className="text-sm font-medium text-gray-500">{t("reports.noData")}</p>
          <p className="mt-1 text-xs text-gray-400">{t("reports.adjustFilters")}</p>
        </div>
      )}

      {/* Table */}
      {!isLoading && !error && data.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50">
                <th className="px-4 py-3 font-medium text-gray-600">{t("reports.colEmpId")}</th>
                <th className="px-4 py-3 font-medium text-gray-600">{t("reports.colDate")}</th>
                <th className="px-4 py-3 font-medium text-gray-600">{t("reports.colFirstIn")}</th>
                <th className="px-4 py-3 font-medium text-gray-600">{t("reports.colLastOut")}</th>
                <th className="px-4 py-3 font-medium text-gray-600">{t("reports.colStatus")}</th>
                <th className="px-4 py-3 font-medium text-gray-600">{t("reports.shiftTime")}</th>
                <th className="px-4 py-3 font-medium text-gray-600">{t("reports.remark")}</th>
                <th className="px-4 py-3 font-medium text-gray-600">{t("reports.reason")}</th>
                <th className="px-4 py-3 font-medium text-gray-600">{t("reports.submissionStatus")}</th>
              </tr>
            </thead>
            <tbody>
              {data.map((row) => (
                <tr key={row.id} className="border-b border-gray-100 last:border-b-0 hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-xs text-gray-700">{row.emp_id}</td>
                  <td className="px-4 py-3 text-gray-700">{row.date}</td>
                  <td className="px-4 py-3 text-gray-700">{formatTime(row.first_clock_in) ?? t("reports.noRecord")}</td>
                  <td className="px-4 py-3 text-gray-700">
                    {isSinglePunch(row.first_clock_in, row.last_clock_out)
                      ? t("reports.noRecord")
                      : (formatTime(row.last_clock_out) ?? t("reports.noRecord"))}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={row.status} label={statusLabelMap[row.status] ?? row.status} />
                  </td>
                  <td className="px-4 py-3 text-gray-700">{row.shift_time ?? "-"}</td>
                  <td className="px-4 py-3 text-gray-700" title={row.remark ?? undefined}>
                    {truncate(row.remark)}
                  </td>
                  <td className="px-4 py-3 text-gray-700" title={row.reason ?? undefined}>
                    {truncate(row.reason)}
                  </td>
                  <td className="px-4 py-3">
                    {row.submission_status ? (
                      <SubmissionBadge
                        status={row.submission_status}
                        label={
                          row.submission_status === "submitted"
                            ? t("reports.submitted")
                            : t("reports.unsubmitted")
                        }
                      />
                    ) : (
                      "-"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Export Section (HR+)
// ---------------------------------------------------------------------------

function ExportSection() {
  const { t } = useTranslation();
  const [startDate, setStartDate] = useState(todayString);
  const [endDate, setEndDate] = useState(todayString);
  const [department, setDepartment] = useState("");
  const [selectedEmployee, setSelectedEmployee] = useState("");
  const [showTerminated, setShowTerminated] = useState(false);
  const [submissionFilter, setSubmissionFilter] = useState<SubmissionFilter>("all");
  const [departments, setDepartments] = useState<readonly string[]>([]);
  const [employees, setEmployees] = useState<readonly Employee[]>([]);
  const [format, setFormat] = useState("csv");
  const [isExporting, setIsExporting] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    async function fetchEmployeesAndDepts() {
      try {
        const qs = showTerminated ? "?include_terminated=true" : "";
        const emps = await apiClient.get<Employee[]>(`/api/employees${qs}`);
        setEmployees(emps);
        const depts = [...new Set(emps.map((e) => e.department))].sort();
        setDepartments(depts);
      } catch {
        // silent
      }
    }
    fetchEmployeesAndDepts();
  }, [showTerminated]);

  // Clear stale selections if they vanish from the dropdown after the toggle changes.
  useEffect(() => {
    if (selectedEmployee && !employees.some((e) => e.emp_id === selectedEmployee)) {
      setSelectedEmployee("");
    }
    if (department && !employees.some((e) => e.department === department)) {
      setDepartment("");
    }
  }, [employees, selectedEmployee, department]);

  async function handleExport(e: React.FormEvent) {
    e.preventDefault();
    setIsExporting(true);
    setMessage(null);

    try {
      const params = new URLSearchParams({
        format,
        start_date: startDate,
        end_date: endDate,
      });
      if (department) params.set("department", department);
      if (selectedEmployee) params.set("emp_id", selectedEmployee);
      if (showTerminated) params.set("include_terminated", "true");
      params.set("submission_filter", submissionFilter);

      const selectedEmp = selectedEmployee
        ? employees.find((e) => e.emp_id === selectedEmployee)
        : undefined;
      const filenameParams = {
        startDate,
        endDate,
        empId: selectedEmployee || undefined,
        empName: selectedEmp?.name,
        department: department || undefined,
      } as const;

      if (format === "csv" || format === "xlsx") {
        const response = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL ?? ""}/api/reports/export?${params.toString()}`,
          {
            headers: {
              Authorization: `Bearer ${localStorage.getItem("access_token") ?? ""}`,
            },
          },
        );
        if (!response.ok) throw new Error(t("reports.exportFailed"));
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = buildExportFilename({ ...filenameParams, format });
        a.click();
        URL.revokeObjectURL(url);
      } else {
        const data = await apiClient.get(
          `/api/reports/export?${params.toString()}`,
        );
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = buildExportFilename({ ...filenameParams, format: "json" });
        a.click();
        URL.revokeObjectURL(url);
      }

      setMessage({ type: "success", text: t("reports.exportSuccess") });
    } catch (err) {
      const msg = err instanceof Error ? err.message : t("reports.exportFailed");
      setMessage({ type: "error", text: msg });
    } finally {
      setIsExporting(false);
    }
  }

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold text-gray-900">
        <Download className="h-5 w-5 text-[#4ec6c1]" />
        {t("reports.exportData")}
      </h2>

      <form onSubmit={handleExport} className="space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-500">{t("reports.startDate")}</label>
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="mt-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm shadow-sm focus:border-[#4ec6c1] focus:ring-2 focus:ring-[#4ec6c1] focus:outline-none" />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500">{t("reports.endDate")}</label>
            <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="mt-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm shadow-sm focus:border-[#4ec6c1] focus:ring-2 focus:ring-[#4ec6c1] focus:outline-none" />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500">{t("reports.department")}</label>
            <select value={department} onChange={(e) => setDepartment(e.target.value)} className="mt-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm shadow-sm focus:border-[#4ec6c1] focus:ring-2 focus:ring-[#4ec6c1] focus:outline-none">
              <option value="">{t("reports.departmentPlaceholder")}</option>
              {departments.map((dept) => (
                <option key={dept} value={dept}>{dept}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500">{t("reports.employee")}</label>
            <select value={selectedEmployee} onChange={(e) => setSelectedEmployee(e.target.value)} className="mt-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm shadow-sm focus:border-[#4ec6c1] focus:ring-2 focus:ring-[#4ec6c1] focus:outline-none">
              <option value="">{t("reports.employeePlaceholder")}</option>
              {employees.map((emp) => (
                <option key={emp.emp_id} value={emp.emp_id}>
                  {emp.emp_id} - {emp.name}
                  {emp.terminated_at ? ` ${t("reports.terminatedOption")}` : ""}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500">&nbsp;</label>
            <label className="mt-1 flex cursor-pointer items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs text-gray-600 shadow-sm">
              <input
                type="checkbox"
                checked={showTerminated}
                onChange={(e) => setShowTerminated(e.target.checked)}
                className="h-3.5 w-3.5 rounded border-gray-300 text-[#4ec6c1] focus:ring-[#4ec6c1]"
              />
              {showTerminated ? t("reports.hideTerminated") : t("reports.showTerminated")}
            </label>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500">{t("reports.submissionFilter")}</label>
            <select
              value={submissionFilter}
              onChange={(e) => setSubmissionFilter(e.target.value as SubmissionFilter)}
              className="mt-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm shadow-sm focus:border-[#4ec6c1] focus:ring-2 focus:ring-[#4ec6c1] focus:outline-none"
              aria-label={`${t("reports.submissionFilter")} export`}
            >
              <option value="all">{t("reports.filterAll")}</option>
              <option value="submitted">{t("reports.filterSubmitted")}</option>
              <option value="unsubmitted">{t("reports.filterUnsubmitted")}</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500">{t("reports.format")}</label>
            <select value={format} onChange={(e) => setFormat(e.target.value)} className="mt-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm shadow-sm focus:border-[#4ec6c1] focus:ring-2 focus:ring-[#4ec6c1] focus:outline-none">
              <option value="csv">CSV</option>
              <option value="json">JSON</option>
              <option value="xlsx">Excel</option>
            </select>
          </div>
          <button
            type="submit"
            disabled={isExporting}
            className="rounded-lg bg-gradient-to-r from-[#4ec6c1] to-[#6dcf7c] px-4 py-1.5 text-sm font-medium text-white hover:from-[#45b5b0] hover:to-[#5fc06e] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isExporting ? t("reports.exporting") : t("reports.export")}
          </button>
        </div>
      </form>

      {message && (
        <div className={`mt-4 rounded-lg border px-3 py-2 text-sm ${
          message.type === "success"
            ? "border-green-200 bg-green-50 text-green-700"
            : "border-red-200 bg-red-50 text-red-700"
        }`}>
          {message.text}
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Generate Summaries Section (ADMIN only)
// ---------------------------------------------------------------------------

function GenerateSection() {
  const { t } = useTranslation();
  const [date, setDate] = useState(todayString);
  const [isGenerating, setIsGenerating] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  async function handleGenerate(e: React.FormEvent) {
    e.preventDefault();
    setIsGenerating(true);
    setMessage(null);

    try {
      const result = await apiClient.post<{ generated_count: number }>(
        `/api/reports/generate?date=${date}`,
      );
      setMessage({
        type: "success",
        text: t("reports.generateSuccess", { count: String(result.generated_count) }),
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : t("reports.generateFailed");
      setMessage({ type: "error", text: msg });
    } finally {
      setIsGenerating(false);
    }
  }

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold text-gray-900">
        <RefreshCw className="h-5 w-5 text-[#4ec6c1]" />
        {t("reports.generateSummaries")}
      </h2>

      <form onSubmit={handleGenerate} className="flex flex-wrap items-end gap-3">
        <div>
          <label className="block text-xs font-medium text-gray-500">{t("reports.generateDate")}</label>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="mt-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm shadow-sm focus:border-[#4ec6c1] focus:ring-2 focus:ring-[#4ec6c1] focus:outline-none" />
        </div>
        <button
          type="submit"
          disabled={isGenerating}
          className="rounded-lg bg-gradient-to-r from-[#4ec6c1] to-[#6dcf7c] px-4 py-1.5 text-sm font-medium text-white hover:from-[#45b5b0] hover:to-[#5fc06e] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isGenerating ? t("reports.generating") : t("reports.generate")}
        </button>
      </form>

      {message && (
        <div className={`mt-4 rounded-lg border px-3 py-2 text-sm ${
          message.type === "success"
            ? "border-green-200 bg-green-50 text-green-700"
            : "border-red-200 bg-red-50 text-red-700"
        }`}>
          {message.text}
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Main Reports Page
// ---------------------------------------------------------------------------

export default function ReportsPage() {
  const { user } = useAuth();
  const { t } = useTranslation();

  const role = user?.role ?? "EMPLOYEE";
  const canAccess = MANAGER_ROLES.includes(role);
  const canExport = HR_ROLES.includes(role);
  const canGenerate = role === "ADMIN";

  if (!canAccess) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-[#e8faf9] via-[#edfbf0] to-[#f5fbe8] px-4 py-8">
        <LanguageSwitcher />
        <div className="mx-auto max-w-4xl">
          <BackButton className="mb-4" />
          <div className="mb-8 flex items-center gap-3">
            <FileText className="h-7 w-7 text-[#4ec6c1]" />
            <h1 className="text-2xl font-bold tracking-tight text-gray-900">
              {t("reports.title")}
            </h1>
          </div>
          <div className="flex min-h-[400px] items-center justify-center">
            <div className="text-center">
              <Shield className="mx-auto h-12 w-12 text-red-400" />
              <h2 className="mt-4 text-lg font-semibold text-gray-900">
                {t("reports.accessDenied")}
              </h2>
              <p className="mt-2 text-sm text-gray-500">
                {t("reports.accessDeniedMessage")}
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
        <BackButton className="mb-4" />
        <div className="mb-8 flex items-center gap-3">
          <FileText className="h-7 w-7 text-[#4ec6c1]" />
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">
            {t("reports.title")}
          </h1>
        </div>

        <div className="space-y-6">
          <DailyReportSection isHr={canExport} />
          {canExport && <ExportSection />}
          {canGenerate && <GenerateSection />}
        </div>
      </div>
    </div>
  );
}
