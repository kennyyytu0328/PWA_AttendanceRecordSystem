"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Clock,
  MapPin,
  CheckCircle,
  AlertTriangle,
  XCircle,
  Loader2,
} from "lucide-react";

import { useAuth } from "@/lib/auth-context";
import { useTranslation } from "@/lib/i18n";
import { useGeolocation } from "@/hooks/useGeolocation";
import { apiClient } from "@/lib/api";
import { BackButton } from "@/components/BackButton";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { deriveDayKindFromDate } from "@/lib/day-kind";
import type { DayKind, PunchResponse, WorkdaysResponse } from "@/types";

async function submitPunch(
  latitude: number,
  longitude: number,
  accuracy: number,
): Promise<PunchResponse> {
  return apiClient.post<PunchResponse>("/api/attendance/punch", {
    latitude,
    longitude,
    accuracy,
  });
}

export default function PunchPage() {
  const router = useRouter();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();
  const { position, requestPosition } = useGeolocation();
  const { t } = useTranslation();

  const [punchResult, setPunchResult] = useState<PunchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  // Today's day_kind — starts from a local weekday guess so the button
  // disables immediately on weekends, then upgrades to the
  // calendar-authoritative answer (which can flip a Saturday back to
  // MAKEUP_WORKDAY on a 補班 day).
  const [todayKind, setTodayKind] = useState<DayKind>(
    deriveDayKindFromDate(new Date()),
  );
  const [reasonText, setReasonText] = useState("");
  const [reasonSubmitted, setReasonSubmitted] = useState(false);
  const [reasonSubmitting, setReasonSubmitting] = useState(false);
  const [reasonError, setReasonError] = useState<string | null>(null);
  const pendingPunch = useRef(false);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/login");
    }
  }, [authLoading, isAuthenticated, router]);

  // Fetch today's calendar day_kind to handle 補班 Saturday — the only flip
  // that can re-enable the button. Sun and weekdays are always correct via
  // the local weekday guess, so skip the probe for them.
  useEffect(() => {
    if (!isAuthenticated) return;
    const today = new Date();
    if (deriveDayKindFromDate(today) !== "REST_DAY") return;
    let cancelled = false;
    const y = today.getFullYear();
    const m = today.getMonth() + 1;
    const iso = today.toISOString().slice(0, 10);
    apiClient
      .get<WorkdaysResponse>(`/api/config/workdays?year=${y}&month=${m}`)
      .then((data) => {
        if (cancelled) return;
        const today_info = data.days.find((d) => d.date === iso);
        if (today_info?.day_kind) {
          setTodayKind(today_info.day_kind);
        }
      })
      .catch(() => {
        // silent — keep the local weekday guess on failure
      });
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated]);

  const isWeekendLocked =
    todayKind === "REGULAR_LEAVE" || todayKind === "REST_DAY";

  // When geolocation resolves after a punch request, submit the punch
  useEffect(() => {
    if (
      !pendingPunch.current ||
      position.latitude === null ||
      position.longitude === null ||
      position.accuracy === null
    ) {
      return;
    }

    pendingPunch.current = false;

    const doSubmit = async () => {
      setIsSubmitting(true);
      try {
        const result = await submitPunch(
          position.latitude!,
          position.longitude!,
          position.accuracy!,
        );
        setPunchResult(result);

        // If tardy and summary exists, check if reason was already submitted
        if (result.summary_id && (result.tardiness_status === "LATE" || result.tardiness_status === "EARLY_LEAVE" || result.tardiness_status === "LATE_AND_EARLY_LEAVE")) {
          try {
            const reasons = await apiClient.get<{ summary_id: number }[]>("/api/reasons/me");
            const alreadySubmitted = reasons.some((r) => r.summary_id === result.summary_id);
            if (alreadySubmitted) {
              setReasonSubmitted(true);
            }
          } catch {
            // silent — form will show, user can still try to submit
          }
        }
      } catch (err) {
        const message =
          err instanceof Error ? err.message : t("punch.punchFailed");
        setError(message);
      } finally {
        setIsSubmitting(false);
      }
    };

    doSubmit();
  }, [position.latitude, position.longitude, position.accuracy, t]);

  const handleReasonSubmit = useCallback(async () => {
    if (!punchResult?.summary_id || !reasonText.trim()) return;

    setReasonSubmitting(true);
    setReasonError(null);

    try {
      await apiClient.post("/api/reasons", {
        summary_id: punchResult.summary_id,
        reason: reasonText.trim(),
      });
      setReasonSubmitted(true);
    } catch (err) {
      const message = err instanceof Error ? err.message : t("punch.reasonSubmitFailed");
      setReasonError(message);
    } finally {
      setReasonSubmitting(false);
    }
  }, [punchResult, reasonText, t]);

  const isLoading = position.loading || isSubmitting;

  const handlePunch = useCallback(async () => {
    setError(null);
    setPunchResult(null);
    setReasonText("");
    setReasonSubmitted(false);
    setReasonError(null);

    if (
      position.latitude !== null &&
      position.longitude !== null &&
      position.accuracy !== null
    ) {
      // Coordinates already available — submit immediately
      setIsSubmitting(true);
      try {
        const result = await submitPunch(
          position.latitude,
          position.longitude,
          position.accuracy,
        );
        setPunchResult(result);

        // If tardy and summary exists, check if reason was already submitted
        if (result.summary_id && (result.tardiness_status === "LATE" || result.tardiness_status === "EARLY_LEAVE" || result.tardiness_status === "LATE_AND_EARLY_LEAVE")) {
          try {
            const reasons = await apiClient.get<{ summary_id: number }[]>("/api/reasons/me");
            const alreadySubmitted = reasons.some((r) => r.summary_id === result.summary_id);
            if (alreadySubmitted) {
              setReasonSubmitted(true);
            }
          } catch {
            // silent
          }
        }
      } catch (err) {
        const message =
          err instanceof Error ? err.message : t("punch.punchFailed");
        setError(message);
      } finally {
        setIsSubmitting(false);
      }
    } else {
      // Request geolocation; useEffect will handle submission when it arrives
      pendingPunch.current = true;
      requestPosition();
    }
  }, [position.latitude, position.longitude, position.accuracy, requestPosition, t]);

  if (authLoading || !isAuthenticated) {
    return null;
  }

  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center bg-gradient-to-br from-[#e8faf9] via-[#edfbf0] to-[#f5fbe8] px-4">
      <BackButton className="absolute left-4 top-4" />
      <LanguageSwitcher />
      <div className="w-full max-w-md space-y-8 text-center">
        {/* User Info */}
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">
            {t("punch.title")}
          </h1>
          {user && (
            <p className="mt-2 text-sm text-gray-500">
              {user.emp_id}
            </p>
          )}
        </div>

        {/* Current Time */}
        <div className="flex items-center justify-center gap-2 text-gray-600">
          <Clock className="h-5 w-5" />
          <span className="text-lg font-medium">
            {new Date().toLocaleTimeString()}
          </span>
        </div>

        {/* Punch Button */}
        <div className="flex justify-center">
          <motion.button
            type="button"
            disabled={isLoading || isWeekendLocked}
            onClick={handlePunch}
            whileTap={isLoading || isWeekendLocked ? undefined : { scale: 0.95 }}
            className="flex h-48 w-48 flex-col items-center justify-center rounded-full bg-gradient-to-br from-[#4ec6c1] to-[#6dcf7c] text-white shadow-xl transition-colors hover:from-[#45b5b0] hover:to-[#5fc06e] focus:ring-4 focus:ring-[#4ec6c1]/40 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isLoading ? (
              <>
                <Loader2 className="h-12 w-12 animate-spin" />
                <span className="mt-2 text-sm font-medium">{t("punch.processing")}</span>
              </>
            ) : (
              <>
                <MapPin className="h-12 w-12" />
                <span className="mt-2 text-lg font-semibold">{t("punch.punchButton")}</span>
              </>
            )}
          </motion.button>
        </div>

        {/* Weekend lock notice */}
        {isWeekendLocked && (
          <div
            role="note"
            data-testid="weekend-lock-notice"
            className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-left text-sm text-amber-800"
          >
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
            <span>
              {todayKind === "REGULAR_LEAVE"
                ? t("punch.regularLeaveNotice")
                : t("punch.restDayNotice")}
            </span>
          </div>
        )}

        {/* Geolocation Error */}
        {position.error && (
          <div
            role="alert"
            className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-left text-sm text-red-700"
          >
            <XCircle className="mt-0.5 h-5 w-5 shrink-0" />
            <span>{position.error}</span>
          </div>
        )}

        {/* API Error */}
        {error && (
          <div
            role="alert"
            className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-left text-sm text-red-700"
          >
            <XCircle className="mt-0.5 h-5 w-5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Punch Result */}
        <AnimatePresence>
          {punchResult && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="space-y-3 rounded-2xl border border-green-200 bg-green-50 p-6"
            >
              <div className="flex items-center justify-center gap-2 text-green-700">
                <CheckCircle className="h-6 w-6" />
                <span className="text-lg font-semibold">{t("punch.punchRecorded")}</span>
              </div>

              <div className="space-y-2 text-sm text-gray-700">
                <div className="flex items-center justify-between">
                  <span className="font-medium">{t("punch.workMode")}</span>
                  <span
                    className={`rounded-full px-3 py-1 text-xs font-semibold ${
                      punchResult.work_mode === "OFFICE"
                        ? "bg-blue-100 text-blue-700"
                        : "bg-purple-100 text-purple-700"
                    }`}
                  >
                    {punchResult.work_mode}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="font-medium">{t("punch.distance")}</span>
                  <span>{punchResult.distance_km} {t("punch.km")}</span>
                </div>
              </div>

              {punchResult.is_low_accuracy && (
                <div className="flex items-center gap-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">
                  <AlertTriangle className="h-4 w-4 shrink-0" />
                  <span>{t("punch.lowAccuracy")}</span>
                </div>
              )}

              {(punchResult.tardiness_status === "LATE" || punchResult.tardiness_status === "LATE_AND_EARLY_LEAVE") && (
                <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                  <AlertTriangle className="h-4 w-4 shrink-0" />
                  <span>{t("punch.lateAlert")}</span>
                </div>
              )}

              {(punchResult.tardiness_status === "EARLY_LEAVE" || punchResult.tardiness_status === "LATE_AND_EARLY_LEAVE") && (
                <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700">
                  <AlertTriangle className="h-4 w-4 shrink-0" />
                  <span>{t("punch.earlyLeaveAlert")}</span>
                </div>
              )}

              {(punchResult.tardiness_status === "LATE" || punchResult.tardiness_status === "EARLY_LEAVE" || punchResult.tardiness_status === "LATE_AND_EARLY_LEAVE") &&
                punchResult.summary_id && !reasonSubmitted && (
                <div className="space-y-2 rounded-lg border border-gray-200 bg-white p-4">
                  <label className="block text-sm font-medium text-gray-700">
                    {t("punch.reasonLabel")}
                  </label>
                  <textarea
                    value={reasonText}
                    onChange={(e) => setReasonText(e.target.value)}
                    maxLength={500}
                    rows={3}
                    placeholder={t("punch.reasonPlaceholder")}
                    className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:border-[#4ec6c1] focus:ring-2 focus:ring-[#4ec6c1] focus:outline-none"
                  />
                  {reasonError && (
                    <div className="text-xs text-red-600">{reasonError}</div>
                  )}
                  <button
                    type="button"
                    disabled={reasonSubmitting || !reasonText.trim()}
                    onClick={handleReasonSubmit}
                    className="rounded-lg bg-gradient-to-r from-[#4ec6c1] to-[#6dcf7c] px-4 py-2 text-sm font-medium text-white hover:from-[#45b5b0] hover:to-[#5fc06e] disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {reasonSubmitting ? t("punch.reasonSubmitting") : t("punch.reasonSubmit")}
                  </button>
                </div>
              )}

              {reasonSubmitted && (
                <div className="flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">
                  <CheckCircle className="h-4 w-4 shrink-0" />
                  <span>{t("punch.reasonSubmitted")}</span>
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
