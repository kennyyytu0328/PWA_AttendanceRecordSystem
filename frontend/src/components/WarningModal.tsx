"use client";

import { memo, useEffect, useRef } from "react";
import { AlertTriangle } from "lucide-react";

import { useTranslation } from "@/lib/i18n";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type AbnormalStatus = "LATE" | "EARLY_LEAVE" | "LATE_AND_EARLY_LEAVE" | "ABSENT";

export interface AbnormalDay {
  readonly date: string;
  readonly status: AbnormalStatus;
  readonly leaveType: string | null;
  readonly remark: string | null;
}

export interface WarningModalProps {
  readonly open: boolean;
  readonly abnormalDays: readonly AbnormalDay[];
  readonly onBackToEdit: () => void;
  readonly onProceed: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const STATUS_I18N_KEY: Readonly<Record<AbnormalStatus, string>> = {
  LATE: "status.late",
  EARLY_LEAVE: "status.early_leave",
  LATE_AND_EARLY_LEAVE: "status.late_and_early_leave",
  ABSENT: "status.absent",
};

const STATUS_BADGE_CLASS: Readonly<Record<AbnormalStatus, string>> = {
  LATE: "bg-yellow-100 text-yellow-800",
  EARLY_LEAVE: "bg-orange-100 text-orange-800",
  LATE_AND_EARLY_LEAVE: "bg-red-100 text-red-800",
  ABSENT: "bg-gray-200 text-gray-800",
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const TITLE_ID = "warning-modal-title";

function WarningModalImpl({ open, abnormalDays, onBackToEdit, onProceed }: WarningModalProps) {
  const { t } = useTranslation();
  const backButtonRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onBackToEdit();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    // Focus the safer (cancel) button when modal opens.
    backButtonRef.current?.focus();
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onBackToEdit]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onBackToEdit}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={TITLE_ID}
        className="w-full max-w-lg rounded-lg bg-white shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start gap-3 border-b border-gray-200 p-5">
          <AlertTriangle className="mt-0.5 h-6 w-6 flex-shrink-0 text-amber-500" aria-hidden />
          <h2 id={TITLE_ID} className="text-lg font-semibold text-gray-900">
            {t("monthlyOverride.warningTitle", { count: abnormalDays.length })}
          </h2>
        </div>

        <div className="p-5">
          <p className="mb-4 text-sm text-gray-700">{t("monthlyOverride.warningBody")}</p>
          <ul className="max-h-80 space-y-2 overflow-y-auto rounded border border-gray-200 bg-gray-50 p-3">
            {abnormalDays.map((day) => (
              <li
                key={day.date}
                className="flex flex-wrap items-center gap-2 text-sm text-gray-800"
              >
                <span className="font-mono">{day.date}</span>
                <span
                  className={`rounded px-2 py-0.5 text-xs font-medium ${
                    STATUS_BADGE_CLASS[day.status]
                  }`}
                >
                  {t(STATUS_I18N_KEY[day.status])}
                </span>
                {day.leaveType ? (
                  <span className="rounded bg-blue-100 px-2 py-0.5 text-xs text-blue-800">
                    {day.leaveType}
                  </span>
                ) : null}
                {day.remark ? (
                  <span className="text-xs text-gray-600">— {day.remark}</span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>

        <div className="flex justify-end gap-2 border-t border-gray-200 p-4">
          <button
            type="button"
            ref={backButtonRef}
            onClick={onBackToEdit}
            className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-gray-400"
          >
            {t("monthlyOverride.backToEdit")}
          </button>
          <button
            type="button"
            onClick={onProceed}
            className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500"
          >
            {t("monthlyOverride.proceed")}
          </button>
        </div>
      </div>
    </div>
  );
}

export const WarningModal = memo(WarningModalImpl);
