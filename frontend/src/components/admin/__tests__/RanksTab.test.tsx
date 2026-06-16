import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

vi.mock("@/lib/i18n", () => ({
  useTranslation: () => ({ t: (k: string) => k, locale: "en", setLocale: vi.fn() }),
}));

const mockList = vi.fn();
const mockUpdate = vi.fn();
vi.mock("@/lib/api/org-hierarchy", () => ({
  ranksApi: {
    list: (...a: unknown[]) => mockList(...a),
    update: (...a: unknown[]) => mockUpdate(...a),
  },
}));

import { RanksTab } from "@/components/admin/RanksTab";

beforeEach(() => {
  mockList.mockReset();
  mockUpdate.mockReset();
});

it("renders ranks from the API in order", async () => {
  mockList.mockResolvedValue({ ranks: ["PRESIDENT", "VP", "MANAGER"] });
  render(<RanksTab />);
  expect(await screen.findByText("PRESIDENT")).toBeInTheDocument();
  expect(screen.getByText("VP")).toBeInTheDocument();
  expect(screen.getByText("MANAGER")).toBeInTheDocument();
});

it("adds a new rank and saves the full list", async () => {
  mockList.mockResolvedValue({ ranks: ["PRESIDENT"] });
  mockUpdate.mockResolvedValue({ ranks: ["PRESIDENT", "AVP"] });
  render(<RanksTab />);
  await screen.findByText("PRESIDENT");

  fireEvent.change(screen.getByPlaceholderText("admin.ranksPlaceholder"), {
    target: { value: "AVP" },
  });
  fireEvent.click(screen.getByTestId("ranks-add-button"));
  expect(screen.getByText("AVP")).toBeInTheDocument();

  fireEvent.click(screen.getByTestId("ranks-save-button"));
  await waitFor(() =>
    expect(mockUpdate).toHaveBeenCalledWith(["PRESIDENT", "AVP"]),
  );
});

it("removes a rank", async () => {
  mockList.mockResolvedValue({ ranks: ["PRESIDENT", "VP"] });
  render(<RanksTab />);
  await screen.findByText("VP");
  fireEvent.click(screen.getByTestId("ranks-remove-VP"));
  expect(screen.queryByText("VP")).not.toBeInTheDocument();
});

it("reorders ranks with the move-up control", async () => {
  mockList.mockResolvedValue({ ranks: ["VP", "PRESIDENT"] });
  mockUpdate.mockResolvedValue({ ranks: ["PRESIDENT", "VP"] });
  render(<RanksTab />);
  await screen.findByText("PRESIDENT");

  fireEvent.click(screen.getByLabelText("admin.ranksMoveUp PRESIDENT"));
  fireEvent.click(screen.getByTestId("ranks-save-button"));
  await waitFor(() =>
    expect(mockUpdate).toHaveBeenCalledWith(["PRESIDENT", "VP"]),
  );
});
