"use client";

import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

import type { WorkdaysResponse, DailyAttendanceSummary, BulkOverrideResponse } from "@/types";

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

vi.mock("@/lib/i18n", () => ({
  useTranslation: () => ({
    locale: "en" as const,
    setLocale: vi.fn(),
    t: (key: string) => {
      const translations: Record<string, string> = {
        "monthlyOverride.title": "Monthly Punch Override",
        "monthlyOverride.subtitle": "Edit clock-in and clock-out times for each workday",
        "monthlyOverride.date": "Date",
        "monthlyOverride.day": "Day",
        "monthlyOverride.type": "Type",
        "monthlyOverride.clockIn": "Clock-in",
        "monthlyOverride.clockOut": "Clock-out",
        "monthlyOverride.status": "Status",
        "monthlyOverride.workday": "Workday",
        "monthlyOverride.holiday": "Holiday",
        "monthlyOverride.weekend": "Weekend",
        "monthlyOverride.makeupWorkday": "Make-up",
        "monthlyOverride.save": "Save All",
        "monthlyOverride.saving": "Saving...",
        "monthlyOverride.saveSuccess": "Punch overrides saved successfully. {count} days updated.",
        "monthlyOverride.saveError": "Failed to save overrides. Please try again.",
        "monthlyOverride.noChanges": "No changes to save.",
        "monthlyOverride.selectEmployee": "Select Employee",
        "monthlyOverride.previousMonth": "Previous Month",
        "monthlyOverride.nextMonth": "Next Month",
        "attendance.statusNormal": "Normal",
        "attendance.statusLate": "Late",
        "attendance.statusEarlyLeave": "Early Leave",
        "attendance.statusLateAndEarlyLeave": "LATE & EARLY LEAVE",
        "attendance.statusAbnormal": "Abnormal",
        "common.backToDashboard": "Back to Dashboard",
        "common.loading": "Loading...",
      };
      return translations[key] ?? key;
    },
  }),
}));

vi.mock("@/components/LanguageSwitcher", () => ({
  LanguageSwitcher: () => null,
}));

vi.mock("@/components/BackButton", () => ({
  BackButton: () => <a href="/dashboard">Back to Dashboard</a>,
}));

const mockGet = vi.fn();
const mockPut = vi.fn();

vi.mock("@/lib/api", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    put: (...args: unknown[]) => mockPut(...args),
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
// Sample data
// ---------------------------------------------------------------------------

const SAMPLE_WORKDAYS: WorkdaysResponse = {
  year: 2026,
  month: 4,
  days: [
    { date: "2026-04-01", weekday_zh: "三", is_holiday: false, description: "", is_makeup_workday: false },
    { date: "2026-04-02", weekday_zh: "四", is_holiday: false, description: "", is_makeup_workday: false },
    { date: "2026-04-03", weekday_zh: "五", is_holiday: true, description: "清明節", is_makeup_workday: false },
    { date: "2026-04-04", weekday_zh: "六", is_holiday: true, description: "Weekend", is_makeup_workday: false },
    { date: "2026-04-05", weekday_zh: "日", is_holiday: true, description: "Weekend", is_makeup_workday: false },
  ],
};

const SAMPLE_SUMMARIES: readonly DailyAttendanceSummary[] = [
  {
    id: 1,
    emp_id: "EMP001",
    date: "2026-04-01",
    first_clock_in: "2026-04-01T09:00:00Z",
    last_clock_out: "2026-04-01T18:00:00Z",
    status: "NORMAL",
  },
];

// ---------------------------------------------------------------------------
// Lazy import
// ---------------------------------------------------------------------------

async function importPage() {
  return await import("@/app/dashboard/monthly-override/page");
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("Monthly Override Page", () => {
  beforeEach(() => {
    vi.resetModules();
    mockPush.mockClear();
    mockGet.mockReset();
    mockPut.mockReset();
    mockUseAuth.mockReturnValue({
      user: { emp_id: "EMP001", role: "EMPLOYEE" },
      token: "fake-token",
      isAuthenticated: true,
      login: vi.fn(),
      logout: vi.fn(),
    });
  });

  it("renders page title", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes("/api/config/workdays")) return Promise.resolve(SAMPLE_WORKDAYS);
      if (url.includes("/api/attendance/summaries")) return Promise.resolve([...SAMPLE_SUMMARIES]);
      return Promise.resolve([]);
    });

    const { default: Page } = await importPage();
    render(<Page />);

    expect(screen.getByText("Monthly Punch Override")).toBeInTheDocument();
  });

  it("displays calendar table with workday rows", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes("/api/config/workdays")) return Promise.resolve(SAMPLE_WORKDAYS);
      if (url.includes("/api/attendance/summaries")) return Promise.resolve([...SAMPLE_SUMMARIES]);
      return Promise.resolve([]);
    });

    const { default: Page } = await importPage();
    render(<Page />);

    await waitFor(() => {
      expect(screen.getByText("2026-04-01")).toBeInTheDocument();
    });

    expect(screen.getByText("2026-04-02")).toBeInTheDocument();
  });

  it("marks holidays as non-editable", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes("/api/config/workdays")) return Promise.resolve(SAMPLE_WORKDAYS);
      if (url.includes("/api/attendance/summaries")) return Promise.resolve([...SAMPLE_SUMMARIES]);
      return Promise.resolve([]);
    });

    const { default: Page } = await importPage();
    render(<Page />);

    await waitFor(() => {
      expect(screen.getByText("清明節")).toBeInTheDocument();
    });
  });

  it("renders Save All button", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes("/api/config/workdays")) return Promise.resolve(SAMPLE_WORKDAYS);
      if (url.includes("/api/attendance/summaries")) return Promise.resolve([...SAMPLE_SUMMARIES]);
      return Promise.resolve([]);
    });

    const { default: Page } = await importPage();
    render(<Page />);

    expect(screen.getByText("Save All")).toBeInTheDocument();
  });

  it("does not render employee selector for EMPLOYEE role", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes("/api/config/workdays")) return Promise.resolve(SAMPLE_WORKDAYS);
      if (url.includes("/api/attendance/summaries")) return Promise.resolve([...SAMPLE_SUMMARIES]);
      return Promise.resolve([]);
    });

    const { default: Page } = await importPage();
    render(<Page />);

    expect(screen.queryByText("Select Employee")).not.toBeInTheDocument();
  });

  it("renders employee selector for HR role", async () => {
    mockUseAuth.mockReturnValue({
      user: { emp_id: "HR001", role: "HR" },
      token: "fake-token",
      isAuthenticated: true,
      login: vi.fn(),
      logout: vi.fn(),
    });

    mockGet.mockImplementation((url: string) => {
      if (url.includes("/api/config/workdays")) return Promise.resolve(SAMPLE_WORKDAYS);
      if (url.includes("/api/attendance/summaries")) return Promise.resolve([...SAMPLE_SUMMARIES]);
      if (url.includes("/api/employees")) {
        return Promise.resolve([
          { emp_id: "EMP001", name: "Alice", department: "Engineering", role: "EMPLOYEE", shift_start_time: "09:00", shift_end_time: "18:00" },
          { emp_id: "EMP002", name: "Bob", department: "Engineering", role: "EMPLOYEE", shift_start_time: "09:00", shift_end_time: "18:00" },
        ]);
      }
      return Promise.resolve([]);
    });

    const { default: Page } = await importPage();
    render(<Page />);

    expect(screen.getByText("Select Employee")).toBeInTheDocument();
  });

  it("shows success message after save", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes("/api/config/workdays")) return Promise.resolve(SAMPLE_WORKDAYS);
      if (url.includes("/api/attendance/summaries")) return Promise.resolve([...SAMPLE_SUMMARIES]);
      return Promise.resolve([]);
    });

    const saveResponse: BulkOverrideResponse = {
      emp_id: "EMP001",
      updated_count: 1,
      results: [
        { date: "2026-04-01", first_clock_in: "08:30", last_clock_out: "18:00", status: "NORMAL" },
      ],
    };
    mockPut.mockResolvedValue(saveResponse);

    const { default: Page } = await importPage();
    render(<Page />);

    await waitFor(() => {
      expect(screen.getByText("2026-04-01")).toBeInTheDocument();
    });

    // Modify a clock-in input
    const clockInInputs = screen.getAllByTestId("clock-in-input");
    fireEvent.change(clockInInputs[0], { target: { value: "08:30" } });

    // Click Save All
    const saveButton = screen.getByText("Save All");
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(screen.getByText(/saved successfully/i)).toBeInTheDocument();
    });
  });
});
