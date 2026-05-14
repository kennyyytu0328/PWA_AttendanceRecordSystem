import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { RemarkCell } from "@/components/RemarkCell";

// Translation just echoes the key so we can assert on keys.
vi.mock("@/lib/i18n", () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));

const LEAVE_TYPES = ["特休", "病假", "事假"] as const;

interface Handlers {
  readonly onLeaveTypeChange: ReturnType<typeof vi.fn>;
  readonly onRemarkChange: ReturnType<typeof vi.fn>;
}

function makeHandlers(): Handlers {
  return {
    onLeaveTypeChange: vi.fn(),
    onRemarkChange: vi.fn(),
  };
}

function renderCell(
  overrides: {
    readonly leaveType?: string | null;
    readonly remark?: string | null;
    readonly disabled?: boolean;
    readonly leaveTypes?: readonly string[];
  } = {},
  handlers: Handlers = makeHandlers(),
) {
  render(
    <RemarkCell
      leaveType={overrides.leaveType ?? null}
      remark={overrides.remark ?? null}
      leaveTypes={[...(overrides.leaveTypes ?? LEAVE_TYPES)]}
      disabled={overrides.disabled}
      onLeaveTypeChange={handlers.onLeaveTypeChange}
      onRemarkChange={handlers.onRemarkChange}
    />,
  );
  return handlers;
}

describe("RemarkCell", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders a dropdown with a None option followed by every provided leaveType", () => {
    renderCell();
    const select = screen.getByLabelText("monthlyOverride.leaveType") as HTMLSelectElement;
    const optionTexts = Array.from(select.options).map((o) => o.textContent);
    expect(optionTexts[0]).toBe("monthlyOverride.leaveTypeNone");
    expect(optionTexts.slice(1)).toEqual([...LEAVE_TYPES]);
  });

  it("calls onLeaveTypeChange with the selected string when a leave type is picked", () => {
    const handlers = renderCell();
    const select = screen.getByLabelText("monthlyOverride.leaveType");
    fireEvent.change(select, { target: { value: "病假" } });
    expect(handlers.onLeaveTypeChange).toHaveBeenCalledWith("病假");
  });

  it("calls onLeaveTypeChange with null when the None option is picked", () => {
    const handlers = renderCell({ leaveType: "特休" });
    const select = screen.getByLabelText("monthlyOverride.leaveType");
    fireEvent.change(select, { target: { value: "" } });
    expect(handlers.onLeaveTypeChange).toHaveBeenCalledWith(null);
  });

  it("calls onRemarkChange with the typed value", () => {
    const handlers = renderCell();
    const input = screen.getByLabelText("monthlyOverride.remark");
    fireEvent.change(input, { target: { value: "Dentist appointment" } });
    expect(handlers.onRemarkChange).toHaveBeenCalledWith("Dentist appointment");
  });

  it("enforces maxLength=500 on the remark input", () => {
    renderCell();
    const input = screen.getByLabelText("monthlyOverride.remark") as HTMLInputElement;
    expect(input.maxLength).toBe(500);
  });

  it("disables both inputs when disabled=true", () => {
    renderCell({ disabled: true });
    expect(screen.getByLabelText("monthlyOverride.leaveType")).toBeDisabled();
    expect(screen.getByLabelText("monthlyOverride.remark")).toBeDisabled();
  });

  it("reflects the controlled leaveType and remark values", () => {
    renderCell({ leaveType: "特休", remark: "annual leave" });
    expect(
      (screen.getByLabelText("monthlyOverride.leaveType") as HTMLSelectElement).value,
    ).toBe("特休");
    expect(
      (screen.getByLabelText("monthlyOverride.remark") as HTMLInputElement).value,
    ).toBe("annual leave");
  });
});
