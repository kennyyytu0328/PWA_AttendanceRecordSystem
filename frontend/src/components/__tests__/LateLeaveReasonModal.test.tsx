import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LateLeaveReasonModal } from "@/components/LateLeaveReasonModal";

vi.mock("@/lib/i18n", () => ({
  useTranslation: () => ({
    t: (k: string) => {
      const map: Record<string, string> = {
        "punch.lateReasonTitle":
          "Your punch time is past your scheduled end time of {time}. Please select a reason:",
        "punch.lateReasonAssignedOvertime":
          "A: Supervisor-assigned overtime (file an overtime request separately)",
        "punch.lateReasonPersonal": "B: Stayed in the office for personal reasons",
        "punch.lateReasonConfirm": "Confirm",
      };
      return map[k] ?? k;
    },
  }),
}));

describe("LateLeaveReasonModal", () => {
  it("renders both options with PERSONAL preselected and no cancel button", () => {
    render(
      <LateLeaveReasonModal
        open
        shiftEnd="17:30"
        value="PERSONAL"
        onChange={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );
    const radios = screen.getAllByRole("radio");
    expect(radios).toHaveLength(2);
    expect(screen.getByRole("radio", { checked: true })).toHaveAttribute(
      "value",
      "PERSONAL",
    );
    // exactly one button: confirm — no cancel path
    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(screen.getByText(/17:30/)).toBeInTheDocument();
  });

  it("confirm fires onConfirm; selecting A fires onChange", () => {
    const onConfirm = vi.fn();
    const onChange = vi.fn();
    render(
      <LateLeaveReasonModal
        open
        shiftEnd="17:30"
        value="PERSONAL"
        onChange={onChange}
        onConfirm={onConfirm}
      />,
    );
    fireEvent.click(screen.getAllByRole("radio")[0]);
    expect(onChange).toHaveBeenCalledWith("ASSIGNED_OVERTIME");
    fireEvent.click(screen.getByRole("button"));
    expect(onConfirm).toHaveBeenCalledOnce();
  });
});
