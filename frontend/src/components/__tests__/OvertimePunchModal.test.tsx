import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OvertimePunchModal } from "@/components/OvertimePunchModal";

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

const DATES: readonly string[] = ["2026-05-16", "2026-05-23"];

function renderModal(
  overrides: { readonly open?: boolean; readonly dates?: readonly string[] } = {},
): { readonly onClose: ReturnType<typeof vi.fn> } {
  const onClose = vi.fn();
  render(
    <OvertimePunchModal
      open={overrides.open ?? true}
      dates={[...(overrides.dates ?? DATES)]}
      onClose={onClose}
    />,
  );
  return { onClose };
}

describe("OvertimePunchModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders nothing when open=false", () => {
    const { container } = render(
      <OvertimePunchModal open={false} dates={[...DATES]} onClose={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the title and lists every offending date", () => {
    renderModal();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(
      screen.getByText("monthlyOverride.overtimePunchTitle"),
    ).toBeInTheDocument();
    expect(screen.getByText("2026-05-16")).toBeInTheDocument();
    expect(screen.getByText("2026-05-23")).toBeInTheDocument();
  });

  it("has no proceed/confirm button — saving is blocked, not optional", () => {
    renderModal();
    expect(
      screen.queryByText("monthlyOverride.proceed"),
    ).not.toBeInTheDocument();
  });

  it("calls onClose when the back-to-edit button is clicked", () => {
    const { onClose } = renderModal();
    fireEvent.click(screen.getByText("monthlyOverride.backToEdit"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when Escape is pressed", () => {
    const { onClose } = renderModal();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose on backdrop click but not on dialog body click", () => {
    const { onClose } = renderModal();
    const dialog = screen.getByRole("dialog");
    fireEvent.click(dialog);
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.click(dialog.parentElement as HTMLElement);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("focuses the back-to-edit button when opened", () => {
    renderModal();
    expect(screen.getByText("monthlyOverride.backToEdit")).toHaveFocus();
  });
});
