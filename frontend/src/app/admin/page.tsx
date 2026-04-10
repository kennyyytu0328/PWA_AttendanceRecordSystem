"use client";

import { Shield, Users, MapPin, Settings, Plus, Pencil, X, Timer, Building2, Trash2, CalendarDays, RefreshCw } from "lucide-react";

import { BackButton } from "@/components/BackButton";
import { useEffect, useState } from "react";

import { apiClient } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useTranslation } from "@/lib/i18n";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import type { Employee, OfficeLocation, Role, SystemConfig, CalendarStatus, CalendarStatusResponse } from "@/types";

// ---------------------------------------------------------------------------
// Role hierarchy helpers
// ---------------------------------------------------------------------------

const ROLE_LEVELS: Readonly<Record<Role, number>> = {
  EMPLOYEE: 0,
  MANAGER: 1,
  HR: 2,
  ADMIN: 3,
};

function hasMinimumRole(userRole: Role, requiredRole: Role): boolean {
  return ROLE_LEVELS[userRole] >= ROLE_LEVELS[requiredRole];
}

// ---------------------------------------------------------------------------
// Employee Management Section
// ---------------------------------------------------------------------------

function EmployeeManagementSection({ userRole, departments }: { readonly userRole: Role; readonly departments: readonly string[] }) {
  const { t } = useTranslation();
  const [employees, setEmployees] = useState<readonly Employee[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [editingEmpId, setEditingEmpId] = useState<string | null>(null);
  const [formMessage, setFormMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  async function fetchEmployees() {
    setIsLoading(true);
    try {
      const data = await apiClient.get<Employee[]>("/api/employees");
      setEmployees(data);
      setError(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : t("admin.failedToLoadEmployees");
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => { fetchEmployees(); }, []);

  async function handleCreate(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setFormMessage(null);
    const form = e.currentTarget;
    const fd = new FormData(form);

    try {
      await apiClient.post("/api/employees", {
        emp_id: fd.get("emp_id"),
        name: fd.get("name"),
        department: fd.get("department"),
        role: fd.get("role"),
        password: fd.get("password"),
        shift_start_time: fd.get("shift_start_time"),
        shift_end_time: fd.get("shift_end_time"),
      });
      setFormMessage({ type: "success", text: t("admin.employeeCreated") });
      setShowCreateForm(false);
      await fetchEmployees();
    } catch (err) {
      const message = err instanceof Error ? err.message : t("admin.failedToCreate");
      setFormMessage({ type: "error", text: message });
    }
  }

  async function handleUpdate(e: React.FormEvent<HTMLFormElement>, empId: string) {
    e.preventDefault();
    setFormMessage(null);
    const form = e.currentTarget;
    const fd = new FormData(form);

    const body: Record<string, string> = {};
    const name = fd.get("name") as string;
    const department = fd.get("department") as string;
    const role = fd.get("role") as string;
    const shiftStart = fd.get("shift_start_time") as string;
    const shiftEnd = fd.get("shift_end_time") as string;
    if (name) body.name = name;
    if (department) body.department = department;
    if (role) body.role = role;
    if (shiftStart) body.shift_start_time = shiftStart;
    if (shiftEnd) body.shift_end_time = shiftEnd;

    try {
      await apiClient.put(`/api/employees/${empId}`, body);
      setFormMessage({ type: "success", text: t("admin.employeeUpdated", { empId }) });
      setEditingEmpId(null);
      await fetchEmployees();
    } catch (err) {
      const message = err instanceof Error ? err.message : t("admin.failedToUpdate");
      setFormMessage({ type: "error", text: message });
    }
  }

  const isAdmin = userRole === "ADMIN";

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Users className="h-5 w-5 text-[#4ec6c1]" />
          <h2 className="text-lg font-semibold text-gray-900">{t("admin.employeeManagement")}</h2>
        </div>
        <button
          type="button"
          onClick={() => { setShowCreateForm(!showCreateForm); setEditingEmpId(null); }}
          className="flex items-center gap-1 rounded-lg bg-gradient-to-r from-[#4ec6c1] to-[#6dcf7c] px-3 py-1.5 text-xs font-medium text-white hover:from-[#45b5b0] hover:to-[#5fc06e]"
        >
          <Plus className="h-3.5 w-3.5" />
          {t("admin.addEmployee")}
        </button>
      </div>

      {formMessage && (
        <div className={`mb-4 rounded-lg border px-3 py-2 text-sm ${
          formMessage.type === "success"
            ? "border-green-200 bg-green-50 text-green-700"
            : "border-red-200 bg-red-50 text-red-700"
        }`}>
          {formMessage.text}
        </div>
      )}

      {/* Create Form */}
      {showCreateForm && (
        <form onSubmit={handleCreate} className="mb-6 space-y-3 rounded-lg border border-blue-200 bg-blue-50 p-4">
          <h3 className="text-sm font-semibold text-gray-800">{t("admin.newEmployee")}</h3>
          <div className="grid grid-cols-2 gap-3">
            <input name="emp_id" required placeholder={t("admin.empIdPlaceholder")} className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm" />
            <input name="name" required placeholder={t("admin.namePlaceholder")} className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm" />
            <select name="department" required className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm">
              <option value="">{t("admin.departmentPlaceholder")}</option>
              {departments.map((dept) => (
                <option key={dept} value={dept}>{dept}</option>
              ))}
            </select>
            <select name="role" required className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm">
              <option value="EMPLOYEE">{t("admin.roleEmployee")}</option>
              <option value="MANAGER">{t("admin.roleManager")}</option>
              <option value="HR">{t("admin.roleHr")}</option>
              {isAdmin && <option value="ADMIN">{t("admin.roleAdmin")}</option>}
            </select>
            <input name="password" type="password" required placeholder={t("admin.passwordPlaceholder")} minLength={6} className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm" />
            <div className="flex gap-2">
              <input name="shift_start_time" type="time" required defaultValue="09:00" className="flex-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm" />
              <input name="shift_end_time" type="time" required defaultValue="18:00" className="flex-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm" />
            </div>
          </div>
          <div className="flex gap-2">
            <button type="submit" className="rounded-lg bg-gradient-to-r from-[#4ec6c1] to-[#6dcf7c] px-4 py-1.5 text-xs font-medium text-white hover:from-[#45b5b0] hover:to-[#5fc06e]">{t("common.create")}</button>
            <button type="button" onClick={() => setShowCreateForm(false)} className="rounded-lg border border-gray-300 px-4 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-100">{t("common.cancel")}</button>
          </div>
        </form>
      )}

      {isLoading && <p className="text-sm text-gray-500">{t("admin.loadingEmployees")}</p>}

      {error && (
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      )}

      {!isLoading && !error && employees.length === 0 && (
        <p className="text-sm text-gray-500">{t("admin.noEmployees")}</p>
      )}

      {!isLoading && !error && employees.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-gray-600">
                <th className="pb-2 pr-4 font-medium">{t("admin.colId")}</th>
                <th className="pb-2 pr-4 font-medium">{t("admin.colName")}</th>
                <th className="pb-2 pr-4 font-medium">{t("admin.colDepartment")}</th>
                <th className="pb-2 pr-4 font-medium">{t("admin.colRole")}</th>
                <th className="pb-2 pr-4 font-medium">{t("admin.colShift")}</th>
                <th className="pb-2 font-medium">{t("admin.colActions")}</th>
              </tr>
            </thead>
            <tbody>
              {employees.map((emp) => (
                editingEmpId === emp.emp_id ? (
                  <tr key={emp.emp_id} className="border-b border-gray-100">
                    <td colSpan={6} className="py-2">
                      <form onSubmit={(e) => handleUpdate(e, emp.emp_id)} className="flex flex-wrap items-end gap-2">
                        <div>
                          <label className="text-xs text-gray-500">{t("admin.editName")}</label>
                          <input name="name" defaultValue={emp.name} className="block w-32 rounded border border-gray-300 px-2 py-1 text-sm" />
                        </div>
                        <div>
                          <label className="text-xs text-gray-500">{t("admin.editDepartment")}</label>
                          <select name="department" defaultValue={emp.department} className="block w-28 rounded border border-gray-300 px-2 py-1 text-sm">
                            {departments.map((dept) => (
                              <option key={dept} value={dept}>{dept}</option>
                            ))}
                          </select>
                        </div>
                        {isAdmin && (
                        <div>
                          <label className="text-xs text-gray-500">{t("admin.editRole")}</label>
                          <select name="role" defaultValue={emp.role} className="block rounded border border-gray-300 px-2 py-1 text-sm">
                            <option value="EMPLOYEE">{t("admin.roleEmployee")}</option>
                            <option value="MANAGER">{t("admin.roleManager")}</option>
                            <option value="HR">{t("admin.roleHr")}</option>
                            <option value="ADMIN">{t("admin.roleAdmin")}</option>
                          </select>
                        </div>
                        )}
                        <div>
                          <label className="text-xs text-gray-500">{t("admin.editShiftStart")}</label>
                          <input name="shift_start_time" type="time" defaultValue={emp.shift_start_time} className="block rounded border border-gray-300 px-2 py-1 text-sm" />
                        </div>
                        <div>
                          <label className="text-xs text-gray-500">{t("admin.editShiftEnd")}</label>
                          <input name="shift_end_time" type="time" defaultValue={emp.shift_end_time} className="block rounded border border-gray-300 px-2 py-1 text-sm" />
                        </div>
                        <button type="submit" className="rounded bg-green-600 px-3 py-1 text-xs font-medium text-white hover:bg-green-500">{t("common.save")}</button>
                        <button type="button" onClick={() => setEditingEmpId(null)} className="rounded border border-gray-300 px-3 py-1 text-xs font-medium text-gray-600 hover:bg-gray-100">
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </form>
                    </td>
                  </tr>
                ) : (
                  <tr key={emp.emp_id} className="border-b border-gray-100 last:border-0">
                    <td className="py-2 pr-4 font-mono text-xs text-gray-600">{emp.emp_id}</td>
                    <td className="py-2 pr-4 text-gray-900">{emp.name}</td>
                    <td className="py-2 pr-4 text-gray-600">{emp.department}</td>
                    <td className="py-2 pr-4">
                      <span className="inline-block rounded-full bg-[#e8faf9] px-2 py-0.5 text-xs font-medium text-[#3a9e99]">{emp.role}</span>
                    </td>
                    <td className="py-2 pr-4 text-gray-600">{emp.shift_start_time} - {emp.shift_end_time}</td>
                    <td className="py-2">
                      <button
                        type="button"
                        onClick={() => { setEditingEmpId(emp.emp_id); setShowCreateForm(false); }}
                        className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-blue-600"
                        title={t("common.edit")}
                      >
                        <Pencil className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                )
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Department Management Section
// ---------------------------------------------------------------------------

function DepartmentManagementSection({
  departments,
  onDepartmentsChange,
}: {
  readonly departments: readonly string[];
  readonly onDepartmentsChange: (departments: readonly string[]) => void;
}) {
  const { t } = useTranslation();
  const [newDept, setNewDept] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  async function saveDepartments(updated: readonly string[]) {
    setIsSubmitting(true);
    setMessage(null);
    try {
      const result = await apiClient.put<{ departments: string[] }>(
        "/api/config/departments",
        { departments: [...updated] },
      );
      onDepartmentsChange(result.departments);
      setMessage({ type: "success", text: t("admin.departmentsUpdated") });
    } catch (err) {
      const msg = err instanceof Error ? err.message : t("admin.failedToUpdateDepartments");
      setMessage({ type: "error", text: msg });
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleAdd() {
    const trimmed = newDept.trim();
    if (!trimmed) return;
    if (departments.includes(trimmed)) {
      setMessage({ type: "error", text: t("admin.departmentExists") });
      return;
    }
    setNewDept("");
    saveDepartments([...departments, trimmed]);
  }

  function handleRemove(dept: string) {
    saveDepartments(departments.filter((d) => d !== dept));
  }

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex items-center gap-2">
        <Building2 className="h-5 w-5 text-blue-600" />
        <h2 className="text-lg font-semibold text-gray-900">
          {t("admin.departmentManagement")}
        </h2>
      </div>

      {/* Department list */}
      {departments.length === 0 && (
        <p className="mb-4 text-sm text-gray-500">{t("admin.noDepartments")}</p>
      )}

      {departments.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-2">
          {departments.map((dept) => (
            <span
              key={dept}
              className="inline-flex items-center gap-1 rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-sm text-gray-700"
            >
              {dept}
              <button
                type="button"
                disabled={isSubmitting}
                onClick={() => handleRemove(dept)}
                className="ml-1 rounded-full p-0.5 text-gray-400 hover:bg-red-100 hover:text-red-600 disabled:opacity-50"
                title={t("admin.removeDepartment")}
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Add department */}
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={newDept}
          onChange={(e) => setNewDept(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); handleAdd(); } }}
          placeholder={t("admin.newDepartmentPlaceholder")}
          className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm shadow-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-500 focus:outline-none"
        />
        <button
          type="button"
          disabled={isSubmitting || !newDept.trim()}
          onClick={handleAdd}
          className="flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Plus className="h-3.5 w-3.5" />
          {t("admin.addDepartment")}
        </button>
      </div>

      {message && (
        <div className={`mt-3 rounded-lg border px-3 py-2 text-sm ${
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
// Office Location Section
// ---------------------------------------------------------------------------

function OfficeLocationSection() {
  const { t } = useTranslation();
  const [latitude, setLatitude] = useState("");
  const [longitude, setLongitude] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [hasExisting, setHasExisting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function fetchLocation() {
      try {
        const data = await apiClient.get<{ key: string; value: OfficeLocation | null }>(
          "/api/config/office-location",
        );
        if (!cancelled) {
          if (data.value && data.value.latitude != null && data.value.longitude != null) {
            setLatitude(String(data.value.latitude));
            setLongitude(String(data.value.longitude));
            setHasExisting(true);
          }
        }
      } catch {
        // If 404 or error, location is simply not set yet — not an error state
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    fetchLocation();
    return () => {
      cancelled = true;
    };
  }, [t]);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    setIsSubmitting(true);

    try {
      const lat = parseFloat(latitude);
      const lng = parseFloat(longitude);

      if (Number.isNaN(lat) || Number.isNaN(lng)) {
        setError(t("admin.invalidCoords"));
        return;
      }

      if (lat < -90 || lat > 90) {
        setError(t("admin.invalidLatitude"));
        return;
      }

      if (lng < -180 || lng > 180) {
        setError(t("admin.invalidLongitude"));
        return;
      }

      await apiClient.put("/api/config/office-location", {
        latitude: lat,
        longitude: lng,
      });

      setHasExisting(true);
      setSuccess(t("admin.locationUpdated"));
    } catch (err) {
      const message =
        err instanceof Error ? err.message : t("admin.failedToUpdateLocation");
      setError(message);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex items-center gap-2">
        <MapPin className="h-5 w-5 text-green-600" />
        <h2 className="text-lg font-semibold text-gray-900">
          {t("admin.officeLocation")}
        </h2>
      </div>

      {isLoading && (
        <p className="text-sm text-gray-500">{t("admin.loadingLocation")}</p>
      )}

      {!isLoading && !hasExisting && !success && (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700">
          {t("admin.locationNotSet")}
        </div>
      )}

      {!isLoading && hasExisting && !success && (
        <div className="mb-4 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-600">
          {t("admin.currentLocation")}: <span className="font-mono font-medium">{latitude}, {longitude}</span>
        </div>
      )}

      {!isLoading && (
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label
                htmlFor="latitude"
                className="block text-sm font-medium text-gray-700"
              >
                {t("admin.latitude")}
              </label>
              <input
                id="latitude"
                type="text"
                inputMode="decimal"
                value={latitude}
                onChange={(e) => setLatitude(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-gray-900 shadow-sm placeholder:text-gray-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-500 focus:outline-none sm:text-sm"
                placeholder={t("admin.latitudePlaceholder")}
              />
            </div>
            <div>
              <label
                htmlFor="longitude"
                className="block text-sm font-medium text-gray-700"
              >
                {t("admin.longitude")}
              </label>
              <input
                id="longitude"
                type="text"
                inputMode="decimal"
                value={longitude}
                onChange={(e) => setLongitude(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-gray-900 shadow-sm placeholder:text-gray-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-500 focus:outline-none sm:text-sm"
                placeholder={t("admin.longitudePlaceholder")}
              />
            </div>
          </div>

          {error && (
            <div
              role="alert"
              className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
            >
              {error}
            </div>
          )}

          {success && (
            <div className="rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">
              {success}
            </div>
          )}

          <button
            type="submit"
            disabled={isSubmitting}
            className="rounded-lg bg-green-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-green-500 focus:ring-2 focus:ring-green-500 focus:ring-offset-2 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSubmitting ? t("admin.updating") : t("admin.updateLocation")}
          </button>
        </form>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Grace Period Section
// ---------------------------------------------------------------------------

function GracePeriodSection() {
  const { t } = useTranslation();
  const [minutes, setMinutes] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function fetchGracePeriod() {
      try {
        const data = await apiClient.get<{ minutes: number }>(
          "/api/config/grace-period",
        );
        if (!cancelled) {
          setMinutes(String(data.minutes));
        }
      } catch (err) {
        if (!cancelled) {
          const message =
            err instanceof Error
              ? err.message
              : t("admin.failedToLoadGracePeriod");
          setError(message);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    fetchGracePeriod();
    return () => {
      cancelled = true;
    };
  }, [t]);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    setIsSubmitting(true);

    try {
      const value = parseInt(minutes, 10);

      if (Number.isNaN(value) || value < 0 || value > 60) {
        setError(t("admin.gracePeriodRange"));
        return;
      }

      await apiClient.put("/api/config/grace-period", {
        minutes: value,
      });

      setSuccess(t("admin.gracePeriodUpdated"));
    } catch (err) {
      const message =
        err instanceof Error ? err.message : t("admin.failedToUpdateGracePeriod");
      setError(message);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex items-center gap-2">
        <Timer className="h-5 w-5 text-amber-600" />
        <h2 className="text-lg font-semibold text-gray-900">
          {t("admin.gracePeriod")}
        </h2>
      </div>

      {isLoading && (
        <p className="text-sm text-gray-500">{t("admin.loadingGracePeriod")}</p>
      )}

      {!isLoading && (
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="max-w-xs">
            <label
              htmlFor="grace-period"
              className="block text-sm font-medium text-gray-700"
            >
              {t("admin.gracePeriodMinutes")}
            </label>
            <input
              id="grace-period"
              type="number"
              min="0"
              max="60"
              value={minutes}
              onChange={(e) => setMinutes(e.target.value)}
              className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-gray-900 shadow-sm placeholder:text-gray-400 focus:border-amber-500 focus:ring-2 focus:ring-amber-500 focus:outline-none sm:text-sm"
            />
          </div>

          {error && (
            <div
              role="alert"
              className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
            >
              {error}
            </div>
          )}

          {success && (
            <div className="rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">
              {success}
            </div>
          )}

          <button
            type="submit"
            disabled={isSubmitting}
            className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-amber-500 focus:ring-2 focus:ring-amber-500 focus:ring-offset-2 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSubmitting ? t("admin.updating") : t("admin.updateGracePeriod")}
          </button>
        </form>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// System Config Section
// ---------------------------------------------------------------------------

function SystemConfigSection() {
  const { t } = useTranslation();
  const [configs, setConfigs] = useState<readonly SystemConfig[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchConfigs() {
      try {
        const data = await apiClient.get<SystemConfig[]>("/api/config");
        if (!cancelled) {
          setConfigs(data);
        }
      } catch (err) {
        if (!cancelled) {
          const message =
            err instanceof Error
              ? err.message
              : t("admin.failedToLoadConfig");
          setError(message);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    fetchConfigs();
    return () => {
      cancelled = true;
    };
  }, [t]);

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex items-center gap-2">
        <Settings className="h-5 w-5 text-purple-600" />
        <h2 className="text-lg font-semibold text-gray-900">{t("admin.systemConfig")}</h2>
      </div>

      {isLoading && (
        <p className="text-sm text-gray-500">{t("admin.loadingConfig")}</p>
      )}

      {error && (
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
        >
          {error}
        </div>
      )}

      {!isLoading && !error && configs.length === 0 && (
        <p className="text-sm text-gray-500">{t("admin.noConfig")}</p>
      )}

      {!isLoading && !error && configs.length > 0 && (
        <div className="space-y-3">
          {configs.map((cfg) => (
            <div
              key={cfg.key}
              className="rounded-lg border border-gray-100 bg-gray-50 p-3"
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-sm font-medium text-gray-800">
                  {cfg.key}
                </span>
              </div>
              {cfg.description && (
                <p className="mt-1 text-xs text-gray-500">{cfg.description}</p>
              )}
              <pre className="mt-2 overflow-x-auto rounded bg-white p-2 text-xs text-gray-700">
                {JSON.stringify(cfg.value, null, 2)}
              </pre>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Calendar Status Section
// ---------------------------------------------------------------------------

function CalendarStatusSection() {
  const { t } = useTranslation();
  const [calendars, setCalendars] = useState<readonly CalendarStatus[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshingYear, setRefreshingYear] = useState<number | null>(null);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  async function fetchStatus() {
    try {
      const data = await apiClient.get<CalendarStatusResponse>("/api/config/workdays/status");
      setCalendars(data.calendars);
      setError(null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : t("calendarStatus.refreshError");
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    fetchStatus();
  }, []);

  async function handleRefresh(year: number) {
    setRefreshingYear(year);
    setMessage(null);
    try {
      const result = await apiClient.post<{ year: number; count: number; message: string }>(
        `/api/config/workdays/refresh?year=${year}`,
        {},
      );
      setMessage({
        type: "success",
        text: t("calendarStatus.refreshSuccess").replace(
          "{count}",
          String(result.count),
        ),
      });
      await fetchStatus();
    } catch (err) {
      const msg = err instanceof Error ? err.message : t("calendarStatus.refreshError");
      setMessage({ type: "error", text: msg });
    } finally {
      setRefreshingYear(null);
    }
  }

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex items-center gap-2">
        <CalendarDays className="h-5 w-5 text-indigo-600" />
        <h2 className="text-lg font-semibold text-gray-900">
          {t("calendarStatus.title")}
        </h2>
      </div>

      {message && (
        <div className={`mb-4 rounded-lg border px-3 py-2 text-sm ${
          message.type === "success"
            ? "border-green-200 bg-green-50 text-green-700"
            : "border-red-200 bg-red-50 text-red-700"
        }`}>
          {message.text}
        </div>
      )}

      {isLoading && (
        <p className="text-sm text-gray-500">{t("common.loading")}</p>
      )}

      {error && (
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {!isLoading && !error && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-gray-600">
                <th className="pb-2 pr-4 font-medium">{t("calendarStatus.year")}</th>
                <th className="pb-2 pr-4 font-medium">{t("calendarStatus.status")}</th>
                <th className="pb-2 pr-4 font-medium">{t("calendarStatus.lastUpdated")}</th>
                <th className="pb-2 pr-4 font-medium">{t("calendarStatus.updatedBy")}</th>
                <th className="pb-2 font-medium">{t("admin.colActions")}</th>
              </tr>
            </thead>
            <tbody>
              {calendars.map((cal) => (
                <tr key={cal.year} className="border-b border-gray-100 last:border-0">
                  <td className="py-2 pr-4 font-mono text-gray-900">{cal.year}</td>
                  <td className="py-2 pr-4">
                    {cal.loaded ? (
                      <span className="inline-block rounded-full bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700">
                        {t("calendarStatus.loaded")} ({cal.entry_count ?? 0} {t("calendarStatus.entries")})
                      </span>
                    ) : (
                      <span className="inline-block rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700">
                        {t("calendarStatus.notLoaded")}
                      </span>
                    )}
                  </td>
                  <td className="py-2 pr-4 text-gray-600">
                    {cal.updated_at ? new Date(cal.updated_at).toLocaleString() : "-"}
                  </td>
                  <td className="py-2 pr-4 text-gray-600">{cal.updated_by ?? "-"}</td>
                  <td className="py-2">
                    <button
                      type="button"
                      disabled={refreshingYear === cal.year}
                      onClick={() => handleRefresh(cal.year)}
                      className="flex items-center gap-1 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <RefreshCw className={`h-3.5 w-3.5 ${refreshingYear === cal.year ? "animate-spin" : ""}`} />
                      {refreshingYear === cal.year ? t("calendarStatus.refreshing") : t("calendarStatus.refresh")}
                    </button>
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
// Access Denied Component
// ---------------------------------------------------------------------------

function AccessDenied() {
  const { t } = useTranslation();

  return (
    <div className="flex min-h-[400px] items-center justify-center">
      <div className="text-center">
        <Shield className="mx-auto h-12 w-12 text-red-400" />
        <h2 className="mt-4 text-lg font-semibold text-gray-900">
          {t("admin.accessDenied")}
        </h2>
        <p className="mt-2 text-sm text-gray-500">
          {t("admin.accessDeniedMessage")}
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Admin Page
// ---------------------------------------------------------------------------

export default function AdminPage() {
  const { user } = useAuth();
  const { t } = useTranslation();
  const [departments, setDepartments] = useState<readonly string[]>([]);

  const userRole = user?.role ?? "EMPLOYEE";
  const canAccessHr = hasMinimumRole(userRole, "HR");
  const canAccessAdmin = hasMinimumRole(userRole, "ADMIN");

  useEffect(() => {
    async function fetchDepartments() {
      try {
        const data = await apiClient.get<{ departments: string[] }>("/api/config/departments");
        setDepartments(data.departments);
      } catch {
        // silent — departments will be empty
      }
    }
    if (canAccessHr) {
      fetchDepartments();
    }
  }, [canAccessHr]);

  if (!canAccessHr) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-[#e8faf9] via-[#edfbf0] to-[#f5fbe8] px-4 py-8">
        <LanguageSwitcher />
        <div className="mx-auto max-w-4xl">
          <BackButton className="mb-4" />
          <div className="mb-8 flex items-center gap-3">
            <Shield className="h-7 w-7 text-[#4ec6c1]" />
            <h1 className="text-2xl font-bold tracking-tight text-gray-900">
              {t("admin.title")}
            </h1>
          </div>
          <AccessDenied />
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
          <Shield className="h-7 w-7 text-[#4ec6c1]" />
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">
            {t("admin.title")}
          </h1>
        </div>

        <div className="space-y-6">
          <DepartmentManagementSection departments={departments} onDepartmentsChange={setDepartments} />
          <EmployeeManagementSection userRole={userRole} departments={departments} />
          <OfficeLocationSection />
          <GracePeriodSection />
          <CalendarStatusSection />
          {canAccessAdmin && <SystemConfigSection />}
        </div>
      </div>
    </div>
  );
}
