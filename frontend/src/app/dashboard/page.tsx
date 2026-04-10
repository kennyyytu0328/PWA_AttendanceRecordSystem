"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  LayoutDashboard,
  Clock,
  Users,
  Settings,
  FileText,
  CalendarDays,
  Calendar,
  MapPin,
  Fingerprint,
  Check,
  LogOut,
} from "lucide-react";

import { useAuth } from "@/lib/auth-context";
import { useTranslation } from "@/lib/i18n";
import { useWebAuthn } from "@/hooks/useWebAuthn";
import { apiClient } from "@/lib/api";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import type { AttendanceLog, Role } from "@/types";

// ---------------------------------------------------------------------------
// Role helpers
// ---------------------------------------------------------------------------

const MANAGER_ROLES: readonly Role[] = ["MANAGER", "HR", "ADMIN"];
const HR_ROLES: readonly Role[] = ["HR", "ADMIN"];

function hasRole(role: Role, allowed: readonly Role[]): boolean {
  return allowed.includes(role);
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function LoadingSkeleton({ loadingText }: { readonly loadingText: string }) {
  return (
    <div className="space-y-4" data-testid="loading-skeleton">
      <p className="text-gray-500">{loadingText}</p>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="h-24 animate-pulse rounded-xl bg-gray-200" />
        <div className="h-24 animate-pulse rounded-xl bg-gray-200" />
      </div>
    </div>
  );
}

interface StatsCardProps {
  readonly title: string;
  readonly value: string;
  readonly icon: React.ReactNode;
}

function StatsCard({ title, value, icon }: StatsCardProps) {
  return (
    <div className="flex items-center gap-4 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-[#e8faf9] text-[#4ec6c1]">
        {icon}
      </div>
      <div>
        <p className="text-sm font-medium text-gray-500">{title}</p>
        <p className="text-2xl font-bold text-gray-900">{value}</p>
      </div>
    </div>
  );
}

interface NavLinkCardProps {
  readonly href: string;
  readonly label: string;
  readonly description: string;
  readonly icon: React.ReactNode;
}

function NavLinkCard({ href, label, description, icon }: NavLinkCardProps) {
  return (
    <Link
      href={href}
      className="flex items-center gap-4 rounded-xl border border-gray-200 bg-white p-5 shadow-sm transition-colors hover:border-[#4ec6c1] hover:bg-[#e8faf9]"
    >
      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gray-100 text-gray-600">
        {icon}
      </div>
      <div>
        <p className="font-semibold text-gray-900">{label}</p>
        <p className="text-sm text-gray-500">{description}</p>
      </div>
    </Link>
  );
}

// ---------------------------------------------------------------------------
// Fingerprint Registration Section
// ---------------------------------------------------------------------------

function FingerprintSection() {
  const { t } = useTranslation();
  const { state: webauthnState, register } = useWebAuthn();
  const [isRegistered, setIsRegistered] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    async function checkStatus() {
      try {
        const res = await apiClient.get<{ registered: boolean }>("/api/auth/webauthn/status");
        setIsRegistered(res.registered);
      } catch {
        // silent
      }
    }
    checkStatus();
  }, []);

  if (!webauthnState.isSupported) {
    return null;
  }

  async function handleRegister() {
    setActionLoading(true);
    setMessage(null);
    try {
      const success = await register();
      if (success) {
        setIsRegistered(true);
        setMessage({ type: "success", text: t("dashboard.fingerprintRegistered") });
      } else {
        setMessage({ type: "error", text: webauthnState.error ?? t("dashboard.fingerprintRegisterFailed") });
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : t("dashboard.fingerprintRegisterFailed");
      setMessage({ type: "error", text: msg });
    } finally {
      setActionLoading(false);
    }
  }

  async function handleRemove() {
    setActionLoading(true);
    setMessage(null);
    try {
      await apiClient.delete("/api/auth/webauthn/credentials");
      setIsRegistered(false);
      setMessage({ type: "success", text: t("dashboard.fingerprintRemoved") });
    } catch (err) {
      const msg = err instanceof Error ? err.message : t("dashboard.fingerprintRemoveFailed");
      setMessage({ type: "error", text: msg });
    } finally {
      setActionLoading(false);
    }
  }

  return (
    <section className="mb-8">
      <div className="flex items-center gap-4 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <div className={`flex h-12 w-12 items-center justify-center rounded-lg ${isRegistered ? "bg-green-50 text-green-500" : "bg-[#e8faf9] text-[#4ec6c1]"}`}>
          {isRegistered ? <Check className="h-6 w-6" /> : <Fingerprint className="h-6 w-6" />}
        </div>
        <div className="flex-1">
          <p className="font-semibold text-gray-900">{t("dashboard.fingerprint")}</p>
          <p className="text-sm text-gray-500">
            {isRegistered ? t("dashboard.fingerprintAlreadyRegistered") : t("dashboard.fingerprintDesc")}
          </p>
          {message && (
            <p className={`mt-1 text-sm ${message.type === "success" ? "text-green-600" : "text-red-600"}`}>
              {message.text}
            </p>
          )}
        </div>
        <div className="flex gap-2">
          {isRegistered ? (
            <button
              type="button"
              onClick={handleRemove}
              disabled={actionLoading}
              className="rounded-lg border border-red-300 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {actionLoading ? t("dashboard.removing") : t("dashboard.removeFingerprint")}
            </button>
          ) : (
            <button
              type="button"
              onClick={handleRegister}
              disabled={actionLoading}
              className="rounded-lg bg-gradient-to-r from-[#4ec6c1] to-[#6dcf7c] px-4 py-2 text-sm font-medium text-white hover:from-[#45b5b0] hover:to-[#5fc06e] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {actionLoading ? t("dashboard.registering") : t("dashboard.registerFingerprint")}
            </button>
          )}
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Dashboard Page
// ---------------------------------------------------------------------------

export default function DashboardPage() {
  const { user, logout } = useAuth();
  const { t } = useTranslation();
  const [logs, setLogs] = useState<readonly AttendanceLog[] | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchToday() {
      try {
        const data = await apiClient.get<AttendanceLog[]>(
          "/api/attendance/today",
        );
        if (!cancelled) {
          setLogs(data);
          setIsLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          const message =
            err instanceof Error ? err.message : t("dashboard.failedToLoad");
          setError(message);
          setIsLoading(false);
        }
      }
    }

    fetchToday();

    return () => {
      cancelled = true;
    };
  }, [t]);

  const role = user?.role ?? "EMPLOYEE";
  const totalPunches = logs?.length ?? 0;
  const latestWorkMode = logs && logs.length > 0 ? logs[logs.length - 1].work_mode : "N/A";

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#e8faf9] via-[#edfbf0] to-[#f5fbe8]">
      <LanguageSwitcher />
      <div className="mx-auto max-w-3xl px-4 py-8">
        {/* Header */}
        <div className="mb-8 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-[#4ec6c1] to-[#6dcf7c] text-white">
            <LayoutDashboard className="h-5 w-5" />
          </div>
          <div className="flex-1">
            <h1 className="text-2xl font-bold tracking-tight text-gray-900">
              {t("dashboard.title")}
            </h1>
            <p className="text-sm text-gray-500">
              {t("dashboard.welcome")}<span className="font-medium text-gray-700">{user?.emp_id ?? t("common.user")}</span>
            </p>
          </div>
          <button
            type="button"
            onClick={logout}
            className="flex items-center gap-2 rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:border-red-300 hover:bg-red-50 hover:text-red-600"
          >
            <LogOut className="h-4 w-4" />
            {t("dashboard.logout")}
          </button>
        </div>

        {/* Stats Section */}
        <section className="mb-8">
          <h2 className="mb-4 text-lg font-semibold text-gray-800">
            {t("dashboard.todayAttendance")}
          </h2>
          {isLoading ? (
            <LoadingSkeleton loadingText={t("common.loading")} />
          ) : error ? (
            <div
              role="alert"
              className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
            >
              {error}
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              <StatsCard
                title={t("dashboard.totalPunches")}
                value={String(totalPunches)}
                icon={<Clock className="h-6 w-6" />}
              />
              <StatsCard
                title={t("dashboard.workMode")}
                value={latestWorkMode}
                icon={<MapPin className="h-6 w-6" />}
              />
            </div>
          )}
        </section>

        {/* Fingerprint Registration */}
        <FingerprintSection />

        {/* Navigation Section */}
        <section>
          <h2 className="mb-4 text-lg font-semibold text-gray-800">
            {t("dashboard.quickActions")}
          </h2>
          <div className="grid gap-3 sm:grid-cols-2">
            <NavLinkCard
              href="/punch"
              label={t("dashboard.punchLabel")}
              description={t("dashboard.punchDesc")}
              icon={<Clock className="h-5 w-5" />}
            />
            <NavLinkCard
              href="/attendance"
              label={t("dashboard.attendanceHistory")}
              description={t("dashboard.attendanceDesc")}
              icon={<CalendarDays className="h-5 w-5" />}
            />
            <NavLinkCard
              href="/dashboard/monthly-override"
              label={t("monthlyOverride.title")}
              description={t("monthlyOverride.subtitle")}
              icon={<Calendar className="h-5 w-5" />}
            />
            {hasRole(role, MANAGER_ROLES) && (
              <NavLinkCard
                href="/team"
                label={t("dashboard.teamAttendance")}
                description={t("dashboard.teamDesc")}
                icon={<Users className="h-5 w-5" />}
              />
            )}
            {hasRole(role, HR_ROLES) && (
              <NavLinkCard
                href="/reports"
                label={t("dashboard.reports")}
                description={t("dashboard.reportsDesc")}
                icon={<FileText className="h-5 w-5" />}
              />
            )}
            {hasRole(role, HR_ROLES) && (
              <NavLinkCard
                href="/admin"
                label={t("dashboard.adminPanel")}
                description={t("dashboard.adminDesc")}
                icon={<Settings className="h-5 w-5" />}
              />
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
