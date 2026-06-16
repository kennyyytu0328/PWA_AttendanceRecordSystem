import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

vi.mock("@/lib/i18n", () => ({
  useTranslation: () => ({ t: (k: string) => k, locale: "en", setLocale: vi.fn() }),
}));

const mockGet = vi.fn();
const mockSet = vi.fn();
vi.mock("@/lib/api/org-hierarchy", () => ({
  orgScopingApi: {
    get: (...a: unknown[]) => mockGet(...a),
    set: (...a: unknown[]) => mockSet(...a),
  },
}));

import { OrgScopingSection } from "@/components/admin/OrgScopingSection";

beforeEach(() => {
  mockGet.mockReset();
  mockSet.mockReset();
});

it("reflects the current enabled state from the API", async () => {
  mockGet.mockResolvedValue({ enabled: true });
  render(<OrgScopingSection />);
  const toggle = await screen.findByTestId("org-scoping-toggle");
  expect(toggle).toHaveAttribute("aria-checked", "true");
  expect(screen.getByText("admin.orgScopingOn")).toBeInTheDocument();
});

it("flips the toggle and persists the negated value", async () => {
  mockGet.mockResolvedValue({ enabled: false });
  mockSet.mockResolvedValue({ enabled: true });
  render(<OrgScopingSection />);
  const toggle = await screen.findByTestId("org-scoping-toggle");
  expect(toggle).toHaveAttribute("aria-checked", "false");

  fireEvent.click(toggle);
  await waitFor(() => expect(mockSet).toHaveBeenCalledWith(true));
  expect(await screen.findByText("admin.orgScopingOn")).toBeInTheDocument();
});
