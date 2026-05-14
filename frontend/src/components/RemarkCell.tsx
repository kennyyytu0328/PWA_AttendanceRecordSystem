"use client";

import { memo, useId, type ChangeEvent } from "react";

import { useTranslation } from "@/lib/i18n";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface RemarkCellProps {
  readonly leaveType: string | null;
  readonly remark: string | null;
  readonly leaveTypes: readonly string[];
  readonly onLeaveTypeChange: (value: string | null) => void;
  readonly onRemarkChange: (value: string) => void;
  readonly disabled?: boolean;
}

const REMARK_MAX_LENGTH = 500;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

function RemarkCellInner({
  leaveType,
  remark,
  leaveTypes,
  onLeaveTypeChange,
  onRemarkChange,
  disabled = false,
}: RemarkCellProps) {
  const { t } = useTranslation();
  const reactId = useId();
  const leaveTypeId = `remark-cell-leave-type-${reactId}`;
  const remarkId = `remark-cell-remark-${reactId}`;

  const handleLeaveTypeChange = (e: ChangeEvent<HTMLSelectElement>) => {
    const v = e.target.value;
    onLeaveTypeChange(v === "" ? null : v);
  };

  const handleRemarkChange = (e: ChangeEvent<HTMLInputElement>) => {
    onRemarkChange(e.target.value);
  };

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={leaveTypeId} className="sr-only">
        {t("monthlyOverride.leaveType")}
      </label>
      <select
        id={leaveTypeId}
        aria-label={t("monthlyOverride.leaveType")}
        value={leaveType ?? ""}
        onChange={handleLeaveTypeChange}
        disabled={disabled}
        className="rounded-lg border border-gray-300 px-2 py-1 text-sm text-gray-900 shadow-sm focus:border-[#4ec6c1] focus:ring-1 focus:ring-[#4ec6c1] focus:outline-none disabled:cursor-not-allowed disabled:bg-gray-100 disabled:text-gray-400"
      >
        <option value="">{t("monthlyOverride.leaveTypeNone")}</option>
        {leaveTypes.map((lt) => (
          <option key={lt} value={lt}>
            {lt}
          </option>
        ))}
      </select>

      <label htmlFor={remarkId} className="sr-only">
        {t("monthlyOverride.remark")}
      </label>
      <input
        id={remarkId}
        type="text"
        aria-label={t("monthlyOverride.remark")}
        value={remark ?? ""}
        onChange={handleRemarkChange}
        maxLength={REMARK_MAX_LENGTH}
        disabled={disabled}
        placeholder={t("monthlyOverride.remark")}
        className="rounded-lg border border-gray-300 px-2 py-1 text-sm text-gray-900 shadow-sm focus:border-[#4ec6c1] focus:ring-1 focus:ring-[#4ec6c1] focus:outline-none disabled:cursor-not-allowed disabled:bg-gray-100 disabled:text-gray-400"
      />
    </div>
  );
}

export const RemarkCell = memo(RemarkCellInner);
RemarkCell.displayName = "RemarkCell";
