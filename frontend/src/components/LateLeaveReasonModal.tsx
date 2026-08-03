"use client";

import { memo } from "react";
import { AlertTriangle } from "lucide-react";

import { useTranslation } from "@/lib/i18n";
import type { LateLeaveReason } from "@/types";

export interface LateLeaveReasonModalProps {
  readonly open: boolean;
  readonly shiftEnd: string;
  readonly value: LateLeaveReason;
  readonly onChange: (value: LateLeaveReason) => void;
  readonly onConfirm: () => void;
}

const TITLE_ID = "late-leave-reason-modal-title";

const OPTIONS: readonly { value: LateLeaveReason; labelKey: string }[] = [
  { value: "ASSIGNED_OVERTIME", labelKey: "punch.lateReasonAssignedOvertime" },
  { value: "PERSONAL", labelKey: "punch.lateReasonPersonal" },
];

/**
 * Confirm-only modal shown when a punch lands after the employee's shift
 * end. No overlay-click or Escape close — the employee must pick a reason
 * (defaults to B/PERSONAL) and confirm before the punch is sent.
 */
function LateLeaveReasonModalImpl({
  open,
  shiftEnd,
  value,
  onChange,
  onConfirm,
}: LateLeaveReasonModalProps) {
  const { t } = useTranslation();
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={TITLE_ID}
        className="w-full max-w-lg rounded-lg bg-white text-left shadow-xl"
      >
        <div className="flex items-start gap-3 border-b border-gray-200 p-5">
          <AlertTriangle className="mt-0.5 h-6 w-6 flex-shrink-0 text-amber-500" aria-hidden />
          <h2 id={TITLE_ID} className="text-base font-semibold text-gray-900">
            {t("punch.lateReasonTitle").replace("{time}", shiftEnd)}
          </h2>
        </div>
        <div className="space-y-3 p-5">
          {OPTIONS.map((opt) => (
            <label
              key={opt.value}
              className="flex cursor-pointer items-start gap-3 rounded-lg border border-gray-200 p-3 text-sm text-gray-800 has-[:checked]:border-[#4ec6c1] has-[:checked]:bg-[#e8faf9]"
            >
              <input
                type="radio"
                name="late-leave-reason"
                value={opt.value}
                checked={value === opt.value}
                onChange={() => onChange(opt.value)}
                className="mt-0.5 h-4 w-4 text-[#4ec6c1] focus:ring-[#4ec6c1]"
              />
              <span>{t(opt.labelKey)}</span>
            </label>
          ))}
        </div>
        <div className="flex justify-end border-t border-gray-200 p-4">
          <button
            type="button"
            onClick={onConfirm}
            className="rounded-md bg-[#4ec6c1] px-6 py-2 text-sm font-medium text-white hover:bg-[#45b5b0] focus:outline-none focus:ring-2 focus:ring-[#4ec6c1]"
          >
            {t("punch.lateReasonConfirm")}
          </button>
        </div>
      </div>
    </div>
  );
}

export const LateLeaveReasonModal = memo(LateLeaveReasonModalImpl);
