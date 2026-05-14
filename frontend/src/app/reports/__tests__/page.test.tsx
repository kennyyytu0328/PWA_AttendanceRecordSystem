import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Role } from "@/types";

// ---------------------------------------------------------------------------
// Mocks (must be hoisted before page import via vi.mock auto-hoisting)
// ---------------------------------------------------------------------------

const authState = {
  user: { emp_id: "HR001", role: "HR" as Role },
};

vi.mock("@/lib/i18n", () => ({
  useTranslation: () => ({
    t: (k: string, params?: Record<string, string | number>) => {
      if (!params) return k;
      return Object.entries(params).reduce<string>(
        (acc, [pk, pv]) => acc.replace(`{${pk}}`, String(pv)),
        k,
      );
    },
    locale: "zh",
    setLocale: vi.fn(),
  }),
}));

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({
    user: authState.user,
    token: "tok",
    isAuthenticated: true,
    isLoading: false,
    login: vi.fn(),
    loginWithToken: vi.fn(),
    logout: vi.fn(),
  }),
}));

vi.mock("@/components/BackButton", () => ({
  BackButton: () => <div data-testid="back-button" />,
}));

vi.mock("@/components/LanguageSwitcher", () => ({
  LanguageSwitcher: () => <div data-testid="lang-switcher" />,
}));

const mockGet = vi.fn();
const mockPost = vi.fn();

vi.mock("@/lib/api", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
  },
}));

// Import after mocks
import ReportsPage from "@/app/reports/page";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

interface MockRow {
  id: number;
  emp_id: string;
  date: string;
  first_clock_in: string | null;
  last_clock_out: string | null;
  status: string;
  shift_time: string | null;
  remark: string | null;
  reason: string | null;
  submission_status: "submitted" | "unsubmitted";
}

function makeRow(overrides: Partial<MockRow> = {}): MockRow {
  return {
    id: 1,
    emp_id: "EMP001",
    date: "2026-05-14",
    first_clock_in: "2026-05-14T01:00:00Z",
    last_clock_out: "2026-05-14T10:00:00Z",
    status: "NORMAL",
    shift_time: "09:00-18:00",
    remark: "morning meeting",
    reason: null,
    submission_status: "unsubmitted",
    ...overrides,
  };
}

beforeEach(() => {
  authState.user = { emp_id: "HR001", role: "HR" };
  mockGet.mockReset();
  mockPost.mockReset();
  // Default: employees endpoint returns empty, daily endpoint returns one row.
  mockGet.mockImplementation((url: string) => {
    if (url.startsWith("/api/employees")) return Promise.resolve([]);
    if (url.startsWith("/api/reports/daily")) return Promise.resolve([makeRow()]);
    return Promise.resolve([]);
  });
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ReportsPage – new columns and submission filter", () => {
  it("renders shift_time, remark, reason, and submission_status columns from API rows", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.startsWith("/api/employees")) return Promise.resolve([]);
      if (url.startsWith("/api/reports/daily")) {
        return Promise.resolve([
          makeRow({
            shift_time: "09:00-18:00",
            remark: "morning meeting",
            reason: "traffic jam",
            submission_status: "submitted",
            status: "LATE",
          }),
        ]);
      }
      return Promise.resolve([]);
    });

    render(<ReportsPage />);

    await waitFor(() => expect(mockGet).toHaveBeenCalled());

    expect(await screen.findByText("09:00-18:00")).toBeInTheDocument();
    expect(screen.getByText("morning meeting")).toBeInTheDocument();
    expect(screen.getByText("traffic jam")).toBeInTheDocument();
    // submitted i18n key (mock returns the key as-is)
    expect(screen.getAllByText("reports.submitted").length).toBeGreaterThan(0);
    // column headers
    expect(screen.getByText("reports.shiftTime")).toBeInTheDocument();
    expect(screen.getByText("reports.remark")).toBeInTheDocument();
    expect(screen.getByText("reports.reason")).toBeInTheDocument();
    expect(screen.getByText("reports.submissionStatus")).toBeInTheDocument();
  });

  it("renders the submission filter for HR users and refetches with submission_filter param when changed", async () => {
    render(<ReportsPage />);

    await waitFor(() => expect(mockGet).toHaveBeenCalled());

    const select = await screen.findByLabelText("reports.submissionFilter");
    expect(select).toBeInTheDocument();

    // Initial fetch should have submission_filter=all
    const initialDailyCall = mockGet.mock.calls.find((c) =>
      String(c[0]).startsWith("/api/reports/daily"),
    );
    expect(initialDailyCall).toBeDefined();
    expect(String(initialDailyCall?.[0])).toContain("submission_filter=all");

    mockGet.mockClear();
    mockGet.mockImplementation((url: string) => {
      if (url.startsWith("/api/employees")) return Promise.resolve([]);
      if (url.startsWith("/api/reports/daily")) return Promise.resolve([makeRow()]);
      return Promise.resolve([]);
    });

    fireEvent.change(select, { target: { value: "unsubmitted" } });

    await waitFor(() => {
      const dailyCalls = mockGet.mock.calls.filter((c) =>
        String(c[0]).startsWith("/api/reports/daily"),
      );
      const latest = dailyCalls[dailyCalls.length - 1];
      expect(latest).toBeDefined();
      expect(String(latest?.[0])).toContain("submission_filter=unsubmitted");
    });
  });

  it("hides the submission filter for MANAGER role", async () => {
    authState.user = { emp_id: "MGR001", role: "MANAGER" };

    render(<ReportsPage />);
    await waitFor(() => expect(mockGet).toHaveBeenCalled());

    expect(screen.queryByLabelText("reports.submissionFilter")).not.toBeInTheDocument();

    // And the request should NOT include submission_filter for non-HR
    const call = mockGet.mock.calls.find((c) =>
      String(c[0]).startsWith("/api/reports/daily"),
    );
    expect(call).toBeDefined();
    expect(String(call?.[0])).not.toContain("submission_filter");
  });

  it("renders LEAVE status with localized label", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.startsWith("/api/employees")) return Promise.resolve([]);
      if (url.startsWith("/api/reports/daily")) {
        return Promise.resolve([
          makeRow({ status: "LEAVE", submission_status: "submitted" }),
        ]);
      }
      return Promise.resolve([]);
    });

    render(<ReportsPage />);

    await waitFor(() => expect(mockGet).toHaveBeenCalled());

    expect(await screen.findByText("status.leave")).toBeInTheDocument();
  });
});
