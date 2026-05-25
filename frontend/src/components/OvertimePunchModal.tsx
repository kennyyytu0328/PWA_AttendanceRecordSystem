"use client";

import { memo, useEffect, useRef } from "react";
import { AlertTriangle } from "lucide-react";

import { useTranslation } from "@/lib/i18n";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface OvertimePunchModalProps {
  readonly open: boolean;
  readonly dates: readonly string[];
  readonly onClose: () => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const TITLE_ID = "overtime-punch-modal-title";

/**
 * Blocking modal shown when the user tries to save a month that has overtime
 * hours set on a day with a missing clock-in or clock-out. Overtime implies
 * actual work, so it always requires both punch times — there is no
 * "proceed anyway" path; the user must go back and supply the times.
 */
function OvertimePunchModalImpl({ open, dates, onClose }: OvertimePunchModalProps) {
  const { t } = useTranslation();
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    closeButtonRef.current?.focus();
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={TITLE_ID}
        className="w-full max-w-lg rounded-lg bg-white shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start gap-3 border-b border-gray-200 p-5">
          <AlertTriangle className="mt-0.5 h-6 w-6 flex-shrink-0 text-red-500" aria-hidden />
          <h2 id={TITLE_ID} className="text-lg font-semibold text-gray-900">
            {t("monthlyOverride.overtimePunchTitle", { count: dates.length })}
          </h2>
        </div>

        <div className="p-5">
          <p className="mb-4 text-sm text-gray-700">
            {t("monthlyOverride.overtimePunchBody")}
          </p>
          <ul className="max-h-80 space-y-2 overflow-y-auto rounded border border-gray-200 bg-gray-50 p-3">
            {dates.map((date) => (
              <li key={date} className="font-mono text-sm text-gray-800">
                {date}
              </li>
            ))}
          </ul>
        </div>

        <div className="flex justify-end border-t border-gray-200 p-4">
          <button
            type="button"
            ref={closeButtonRef}
            onClick={onClose}
            className="rounded-md bg-[#4ec6c1] px-4 py-2 text-sm font-medium text-white hover:bg-[#45b5b0] focus:outline-none focus:ring-2 focus:ring-[#4ec6c1]"
          >
            {t("monthlyOverride.backToEdit")}
          </button>
        </div>
      </div>
    </div>
  );
}

export const OvertimePunchModal = memo(OvertimePunchModalImpl);
