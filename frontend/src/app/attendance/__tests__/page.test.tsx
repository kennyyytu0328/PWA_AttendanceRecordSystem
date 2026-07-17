import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Role } from "@/types";

// ---------------------------------------------------------------------------
// Mocks (hoisted)
// ---------------------------------------------------------------------------

const authState: { user: { emp_id: string; role: Role } } = {
  user: { emp_id: "EMP001", role: "EMPLOYEE" },
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

import AttendancePage from "@/app/attendance/page";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const LOGS = [
  {
    id: 1,
    emp_id: "EMP001",
    timestamp: "2026-07-14T08:14:00",
    work_mode: "OFFICE" as const,
    latitude: 0,
    longitude: 0,
    accuracy: 10,
    ip_address: null,
    is_overridden: false,
    override_reason: null,
  },
  {
    id: 2,
    emp_id: "EMP001",
    timestamp: "2026-07-14T08:14:30",
    work_mode: "WFH" as const,
    latitude: 24.7752,
    longitude: 121.0445,
    accuracy: 10,
    ip_address: null,
    is_overridden: true,
    override_reason: "correction",
  },
  {
    id: 3,
    emp_id: "EMP001",
    timestamp: "2026-07-14T17:38:00",
    work_mode: "OFFICE" as const,
    latitude: 0,
    longitude: 0,
    accuracy: 10,
    ip_address: null,
    is_overridden: false,
    override_reason: null,
  },
];

beforeEach(() => {
  mockGet.mockReset();
  authState.user = { emp_id: "EMP001", role: "EMPLOYEE" };
  mockGet.mockImplementation((url: string) => {
    if (url.startsWith("/api/attendance/summaries")) return Promise.resolve([]);
    if (url.startsWith("/api/attendance")) return Promise.resolve(LOGS);
    return Promise.resolve([]);
  });
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AttendancePage overridden rows", () => {
  it("hides overridden audit rows", async () => {
    render(<AttendancePage />);

    await waitFor(() => {
      expect(screen.getAllByRole("row").length).toBeGreaterThan(1);
    });

    expect(screen.queryByText("24.7752, 121.0445")).not.toBeInTheDocument();

    // header row + exactly 2 data rows
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });

  it("still renders active punches", async () => {
    render(<AttendancePage />);

    await waitFor(() => {
      expect(screen.getAllByRole("row").length).toBeGreaterThan(1);
    });

    expect(screen.getByText("08:14 AM")).toBeInTheDocument();
    expect(screen.getByText("05:38 PM")).toBeInTheDocument();
  });
});
