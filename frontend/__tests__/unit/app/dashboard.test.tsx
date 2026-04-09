"use client";

import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

import type { AttendanceLog, AuthUser } from "@/types";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockPush = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

const mockUseAuth = vi.fn<() => {
  user: AuthUser | null;
  token: string | null;
  isAuthenticated: boolean;
  login: () => Promise<void>;
  logout: () => void;
}>();

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => mockUseAuth(),
}));

const mockGet = vi.fn();

vi.mock("@/lib/api", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
  },
  ApiError: class ApiError extends Error {
    status: number;
    detail: string;
    constructor(status: number, detail: string) {
      super(detail);
      this.name = "ApiError";
      this.status = status;
      this.detail = detail;
    }
  },
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeAuthReturn(overrides: Partial<ReturnType<typeof mockUseAuth>> = {}) {
  return {
    user: { emp_id: "EMP001", role: "EMPLOYEE" as const },
    token: "fake-token",
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
    ...overrides,
  };
}

const TODAY_LOGS: readonly AttendanceLog[] = [
  {
    id: 1,
    emp_id: "EMP001",
    timestamp: "2026-03-19T09:00:00Z",
    work_mode: "WFO",
    latitude: 25.033,
    longitude: 121.564,
    accuracy: 10,
    ip_address: null,
    is_overridden: false,
    override_reason: null,
  },
  {
    id: 2,
    emp_id: "EMP001",
    timestamp: "2026-03-19T12:00:00Z",
    work_mode: "WFO",
    latitude: 25.033,
    longitude: 121.564,
    accuracy: 10,
    ip_address: null,
    is_overridden: false,
    override_reason: null,
  },
];

// ---------------------------------------------------------------------------
// Lazy import (after mocks)
// ---------------------------------------------------------------------------

async function importDashboardPage() {
  return await import("@/app/dashboard/page");
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("Dashboard Page", () => {
  beforeEach(() => {
    vi.resetModules();
    mockPush.mockClear();
    mockUseAuth.mockClear();
    mockGet.mockClear();
  });

  it("renders welcome message with user info", async () => {
    mockUseAuth.mockReturnValue(makeAuthReturn());
    mockGet.mockResolvedValue(TODAY_LOGS);

    const { default: DashboardPage } = await importDashboardPage();

    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText(/welcome/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/EMP001/)).toBeInTheDocument();
  });

  it("shows today's attendance data after loading", async () => {
    mockUseAuth.mockReturnValue(makeAuthReturn());
    mockGet.mockResolvedValue(TODAY_LOGS);

    const { default: DashboardPage } = await importDashboardPage();

    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText(/2/)).toBeInTheDocument();
    });
    expect(screen.getByText(/WFO/i)).toBeInTheDocument();
  });

  it("shows loading state while fetching", async () => {
    mockUseAuth.mockReturnValue(makeAuthReturn());
    // Never resolve — keep loading
    mockGet.mockReturnValue(new Promise(() => {}));

    const { default: DashboardPage } = await importDashboardPage();

    render(<DashboardPage />);

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it("shows navigation links for all roles", async () => {
    mockUseAuth.mockReturnValue(makeAuthReturn());
    mockGet.mockResolvedValue(TODAY_LOGS);

    const { default: DashboardPage } = await importDashboardPage();

    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByRole("link", { name: /punch/i })).toBeInTheDocument();
    });
    expect(
      screen.getByRole("link", { name: /attendance/i }),
    ).toBeInTheDocument();
  });

  it("MANAGER sees team attendance link", async () => {
    mockUseAuth.mockReturnValue(
      makeAuthReturn({
        user: { emp_id: "MGR001", role: "MANAGER" },
      }),
    );
    mockGet.mockResolvedValue([]);

    const { default: DashboardPage } = await importDashboardPage();

    render(<DashboardPage />);

    await waitFor(() => {
      expect(
        screen.getByRole("link", { name: /team/i }),
      ).toBeInTheDocument();
    });
  });

  it("EMPLOYEE does not see admin links", async () => {
    mockUseAuth.mockReturnValue(makeAuthReturn());
    mockGet.mockResolvedValue(TODAY_LOGS);

    const { default: DashboardPage } = await importDashboardPage();

    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByRole("link", { name: /punch/i })).toBeInTheDocument();
    });

    expect(screen.queryByRole("link", { name: /team/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /report/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /config/i })).not.toBeInTheDocument();
  });
});
