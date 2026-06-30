import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Role } from "@/types";

// ---------------------------------------------------------------------------
// Mocks (hoisted)
// ---------------------------------------------------------------------------

const authState: { user: { emp_id: string; role: Role } } = {
  user: { emp_id: "MGR001", role: "MANAGER" },
};

const stableT = (k: string) => k;
vi.mock("@/lib/i18n", () => ({
  useTranslation: () => ({ t: stableT, locale: "en", setLocale: vi.fn() }),
}));

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({ user: authState.user }),
}));

vi.mock("@/components/BackButton", () => ({
  BackButton: () => <div data-testid="back-button" />,
}));
vi.mock("@/components/LanguageSwitcher", () => ({
  LanguageSwitcher: () => <div data-testid="lang-switcher" />,
}));

const mockGet = vi.fn();
vi.mock("@/lib/api", () => ({
  apiClient: { get: (...args: unknown[]) => mockGet(...args) },
}));

import TeamPage from "@/app/team/page";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const LOG = {
  id: 1,
  emp_id: "EMP001",
  timestamp: "2026-06-30T01:00:00",
  work_mode: "OFFICE" as const,
  latitude: 25.0,
  longitude: 121.5,
  accuracy: 10,
  is_overridden: false,
};

beforeEach(() => {
  mockGet.mockReset();
  authState.user = { emp_id: "MGR001", role: "MANAGER" };
  mockGet.mockImplementation((url: string) => {
    if (url.startsWith("/api/attendance/")) return Promise.resolve([LOG]);
    if (url.startsWith("/api/reports/daily")) {
      return Promise.resolve([
        { emp_id: "EMP001", name: "Alice Wang", date: "2026-06-30", status: "NORMAL" },
      ]);
    }
    return Promise.resolve([]);
  });
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("TeamPage name column", () => {
  it("renders a Name header", async () => {
    render(<TeamPage />);
    await waitFor(() => {
      expect(screen.getByText("team.name")).toBeInTheDocument();
    });
  });

  it("shows the employee name next to the emp_id from the daily report", async () => {
    render(<TeamPage />);
    await waitFor(() => {
      expect(screen.getByText("EMP001")).toBeInTheDocument();
    });
    expect(screen.getByText("Alice Wang")).toBeInTheDocument();
  });
});
