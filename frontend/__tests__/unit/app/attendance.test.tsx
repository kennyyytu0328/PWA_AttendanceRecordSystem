"use client";

import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

import type { AttendanceLog, WorkMode } from "@/types";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockPush = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

const mockUseAuth = vi.fn();

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

function buildLog(overrides: Partial<AttendanceLog> = {}): AttendanceLog {
  return {
    id: 1,
    emp_id: "EMP001",
    timestamp: "2026-03-19T09:00:00Z",
    work_mode: "WFO" as WorkMode,
    latitude: 13.7563,
    longitude: 100.5018,
    accuracy: 10,
    ip_address: "192.168.1.1",
    is_overridden: false,
    override_reason: null,
    ...overrides,
  };
}

const SAMPLE_LOGS: readonly AttendanceLog[] = [
  buildLog({ id: 1, timestamp: "2026-03-19T09:00:00Z", work_mode: "WFO" }),
  buildLog({ id: 2, timestamp: "2026-03-18T09:15:00Z", work_mode: "WFH" }),
  buildLog({
    id: 3,
    timestamp: "2026-03-17T09:30:00Z",
    work_mode: "WFO",
    is_overridden: true,
    override_reason: "Manager correction",
  }),
];

// ---------------------------------------------------------------------------
// Lazy imports (after mocks are registered)
// ---------------------------------------------------------------------------

async function importAttendancePage() {
  return await import("@/app/attendance/page");
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("Attendance History Page", () => {
  beforeEach(() => {
    vi.resetModules();
    mockPush.mockClear();
    mockGet.mockReset();
    mockUseAuth.mockReturnValue({
      user: { emp_id: "EMP001", role: "EMPLOYEE" },
      token: "fake-token",
      isAuthenticated: true,
      login: vi.fn(),
      logout: vi.fn(),
    });
  });

  it("renders attendance history heading", async () => {
    mockGet.mockResolvedValueOnce([]);

    const { default: AttendancePage } = await importAttendancePage();
    render(<AttendancePage />);

    expect(
      screen.getByRole("heading", { name: /attendance history/i }),
    ).toBeInTheDocument();
  });

  it("shows loading state while fetching", async () => {
    // Never-resolving promise to keep loading state
    mockGet.mockReturnValue(new Promise(() => {}));

    const { default: AttendancePage } = await importAttendancePage();
    render(<AttendancePage />);

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it("displays attendance records in a table", async () => {
    mockGet.mockResolvedValueOnce([...SAMPLE_LOGS]);

    const { default: AttendancePage } = await importAttendancePage();
    render(<AttendancePage />);

    await waitFor(() => {
      expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();
    });

    // Should show date/time information from logs
    expect(screen.getByText(/2026-03-19/)).toBeInTheDocument();
    expect(screen.getByText(/2026-03-18/)).toBeInTheDocument();
    expect(screen.getByText(/2026-03-17/)).toBeInTheDocument();
  });

  it("shows work mode badges with correct styling", async () => {
    mockGet.mockResolvedValueOnce([...SAMPLE_LOGS]);

    const { default: AttendancePage } = await importAttendancePage();
    render(<AttendancePage />);

    await waitFor(() => {
      expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();
    });

    const wfoBadges = screen.getAllByText("WFO");
    const wfhBadges = screen.getAllByText("WFH");

    expect(wfoBadges.length).toBeGreaterThanOrEqual(1);
    expect(wfhBadges.length).toBeGreaterThanOrEqual(1);

    // WFO badge should have blue styling
    expect(wfoBadges[0].className).toMatch(/blue/);
    // WFH badge should have green styling
    expect(wfhBadges[0].className).toMatch(/green/);
  });

  it("shows empty state when no records found", async () => {
    mockGet.mockResolvedValueOnce([]);

    const { default: AttendancePage } = await importAttendancePage();
    render(<AttendancePage />);

    await waitFor(() => {
      expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();
    });

    expect(screen.getByText(/no attendance records/i)).toBeInTheDocument();
  });

  it("shows override indicator for overridden entries", async () => {
    mockGet.mockResolvedValueOnce([...SAMPLE_LOGS]);

    const { default: AttendancePage } = await importAttendancePage();
    render(<AttendancePage />);

    await waitFor(() => {
      expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();
    });

    expect(screen.getByText(/overridden/i)).toBeInTheDocument();
  });

  it("renders date filter inputs", async () => {
    mockGet.mockResolvedValueOnce([]);

    const { default: AttendancePage } = await importAttendancePage();
    render(<AttendancePage />);

    const startDateInput = screen.getByLabelText(/start date/i);
    const endDateInput = screen.getByLabelText(/end date/i);

    expect(startDateInput).toBeInTheDocument();
    expect(endDateInput).toBeInTheDocument();
    expect(startDateInput).toHaveAttribute("type", "date");
    expect(endDateInput).toHaveAttribute("type", "date");
  });
});
