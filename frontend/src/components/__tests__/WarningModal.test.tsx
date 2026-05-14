import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { WarningModal, type AbnormalDay } from "@/components/WarningModal";

vi.mock("@/lib/i18n", () => ({
  useTranslation: () => ({
    t: (k: string, params?: Record<string, string | number>) => {
      if (!params) return k;
      return Object.entries(params).reduce<string>(
        (acc, [pk, pv]) => acc.replace(`{${pk}}`, String(pv)),
        k,
      );
    },
  }),
}));

const DAYS: readonly AbnormalDay[] = [
  { date: "2026-05-01", status: "LATE", leaveType: null, remark: null },
  { date: "2026-05-02", status: "EARLY_LEAVE", leaveType: "特休", remark: null },
  { date: "2026-05-03", status: "ABSENT", leaveType: null, remark: "sick" },
];

interface Handlers {
  readonly onBackToEdit: ReturnType<typeof vi.fn>;
  readonly onProceed: ReturnType<typeof vi.fn>;
}

function renderModal(
  overrides: { readonly open?: boolean; readonly abnormalDays?: readonly AbnormalDay[] } = {},
): Handlers {
  const handlers: Handlers = {
    onBackToEdit: vi.fn(),
    onProceed: vi.fn(),
  };
  render(
    <WarningModal
      open={overrides.open ?? true}
      abnormalDays={[...(overrides.abnormalDays ?? DAYS)]}
      onBackToEdit={handlers.onBackToEdit}
      onProceed={handlers.onProceed}
    />,
  );
  return handlers;
}

describe("WarningModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders nothing when open=false", () => {
    const { container } = render(
      <WarningModal
        open={false}
        abnormalDays={[...DAYS]}
        onBackToEdit={vi.fn()}
        onProceed={vi.fn()}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders count in title when open with 3 abnormal days", () => {
    renderModal();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(/3/)).toBeInTheDocument();
  });

  it("lists each abnormal day's date and status", () => {
    renderModal();
    expect(screen.getByText("2026-05-01")).toBeInTheDocument();
    expect(screen.getByText("2026-05-02")).toBeInTheDocument();
    expect(screen.getByText("2026-05-03")).toBeInTheDocument();
    expect(screen.getByText("status.late")).toBeInTheDocument();
    expect(screen.getByText("status.early_leave")).toBeInTheDocument();
    expect(screen.getByText("status.absent")).toBeInTheDocument();
  });

  it("calls onBackToEdit when 返回修改 is clicked", () => {
    const handlers = renderModal();
    fireEvent.click(screen.getByText("monthlyOverride.backToEdit"));
    expect(handlers.onBackToEdit).toHaveBeenCalledTimes(1);
    expect(handlers.onProceed).not.toHaveBeenCalled();
  });

  it("calls onProceed when 繼續送出 is clicked", () => {
    const handlers = renderModal();
    fireEvent.click(screen.getByText("monthlyOverride.proceed"));
    expect(handlers.onProceed).toHaveBeenCalledTimes(1);
    expect(handlers.onBackToEdit).not.toHaveBeenCalled();
  });

  it("calls onBackToEdit when Escape is pressed", () => {
    const handlers = renderModal();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(handlers.onBackToEdit).toHaveBeenCalledTimes(1);
  });

  it("calls onBackToEdit when the backdrop is clicked but not when dialog body is clicked", () => {
    const handlers = renderModal();
    const dialog = screen.getByRole("dialog");
    fireEvent.click(dialog);
    expect(handlers.onBackToEdit).not.toHaveBeenCalled();
    const backdrop = dialog.parentElement as HTMLElement;
    fireEvent.click(backdrop);
    expect(handlers.onBackToEdit).toHaveBeenCalledTimes(1);
  });

  it("focuses the back-to-edit button when opened", () => {
    renderModal();
    expect(screen.getByText("monthlyOverride.backToEdit")).toHaveFocus();
  });
});
