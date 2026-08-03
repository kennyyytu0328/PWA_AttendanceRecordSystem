import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

vi.mock("@/lib/i18n", () => ({
  useTranslation: () => ({ t: (k: string) => k, locale: "en", setLocale: vi.fn() }),
}));

const mockedGet = vi.fn();
const mockedSet = vi.fn();
vi.mock("@/lib/api/override-lock", () => ({
  overrideLockApi: {
    get: (...a: unknown[]) => mockedGet(...a),
    set: (...a: unknown[]) => mockedSet(...a),
  },
}));

import { OverrideLockSection } from "@/components/admin/OverrideLockSection";

beforeEach(() => {
  mockedGet.mockReset();
  mockedSet.mockReset();
});

it("reflects the current locked state from the API", async () => {
  mockedGet.mockResolvedValue({ locked: true });
  render(<OverrideLockSection />);
  const toggle = await screen.findByTestId("override-lock-toggle");
  expect(toggle).toHaveAttribute("aria-checked", "true");
  expect(screen.getByText("admin.overrideLockOn")).toBeInTheDocument();
});

it("shows current state and toggles lock via PUT", async () => {
  mockedGet.mockResolvedValue({ locked: false });
  mockedSet.mockResolvedValue({ locked: true });
  render(<OverrideLockSection />);
  const btn = await screen.findByTestId("override-lock-toggle");
  fireEvent.click(btn);
  await waitFor(() => expect(mockedSet).toHaveBeenCalledWith(true));
  expect(await screen.findByText("admin.overrideLockOn")).toBeInTheDocument();
});
