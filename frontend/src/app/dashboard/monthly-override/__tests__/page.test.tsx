import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import MonthlyOverridePage from "@/app/dashboard/monthly-override/page";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

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
    user: { emp_id: "EMP001", role: "EMPLOYEE" },
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
const mockPut = vi.fn();
const mockPost = vi.fn();

vi.mock("@/lib/api", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    put: (...args: unknown[]) => mockPut(...args),
    post: (...args: unknown[]) => mockPost(...args),
  },
}));

const mockListLeaveTypes = vi.fn();
vi.mock("@/lib/api/leave-types", () => ({
  leaveTypesApi: {
    list: (...args: unknown[]) => mockListLeaveTypes(...args),
    update: vi.fn(),
  },
}));

const mockSubmit = vi.fn();
const mockGetStatus = vi.fn();
vi.mock("@/lib/api/monthly-submissions", () => ({
  monthlySubmissionsApi: {
    submit: (...args: unknown[]) => mockSubmit(...args),
    getStatus: (...args: unknown[]) => mockGetStatus(...args),
  },
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

interface WorkdayResp {
  year: number;
  month: number;
  days: ReadonlyArray<{
    date: string;
    weekday_zh: string;
    is_holiday: boolean;
    description: string;
    is_makeup_workday: boolean;
  }>;
}

function buildWorkdays(): WorkdayResp {
  // Three workdays for testing.
  return {
    year: 2026,
    month: 5,
    days: [
      {
        date: "2026-05-01",
        weekday_zh: "週五",
        is_holiday: false,
        description: "",
        is_makeup_workday: false,
      },
      {
        date: "2026-05-02",
        weekday_zh: "週六",
        is_holiday: false,
        description: "",
        is_makeup_workday: false,
      },
      {
        date: "2026-05-03",
        weekday_zh: "週日",
        is_holiday: false,
        description: "",
        is_makeup_workday: false,
      },
    ],
  };
}

function buildSummaries(): ReadonlyArray<{
  id: number;
  emp_id: string;
  date: string;
  first_clock_in: string | null;
  last_clock_out: string | null;
  status: string;
  leave_type: string | null;
  remark: string | null;
}> {
  return [
    {
      id: 1,
      emp_id: "EMP001",
      date: "2026-05-01",
      first_clock_in: "2026-05-01T09:30:00",
      last_clock_out: "2026-05-01T18:00:00",
      status: "LATE",
      leave_type: null,
      remark: null,
    },
    {
      id: 2,
      emp_id: "EMP001",
      date: "2026-05-02",
      first_clock_in: "2026-05-02T09:00:00",
      last_clock_out: "2026-05-02T18:00:00",
      status: "NORMAL",
      leave_type: null,
      remark: null,
    },
  ];
}

function wireApi(): void {
  mockGet.mockImplementation((url: string) => {
    if (url.startsWith("/api/config/workdays")) {
      return Promise.resolve(buildWorkdays());
    }
    if (url.startsWith("/api/attendance/summaries")) {
      return Promise.resolve(buildSummaries());
    }
    if (url.startsWith("/api/employees")) {
      return Promise.resolve([]);
    }
    return Promise.reject(new Error(`unmocked get: ${url}`));
  });
  mockPut.mockResolvedValue({
    emp_id: "EMP001",
    updated_count: 1,
    results: [],
  });
  mockListLeaveTypes.mockResolvedValue({
    leave_types: ["特休", "病假", "事假"],
  });
}

async function renderPage(): Promise<void> {
  await act(async () => {
    render(<MonthlyOverridePage />);
  });
  // Wait for initial data load.
  await waitFor(() => {
    expect(screen.getByText("2026-05-01")).toBeInTheDocument();
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("MonthlyOverridePage submission flow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    wireApi();
  });

  it("renders the 'notSubmitted' badge when status returns submitted=false", async () => {
    mockGetStatus.mockResolvedValue({ submitted: false, submitted_at: null });
    await renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("submission-status-badge")).toHaveTextContent(
        "monthlyOverride.notSubmitted",
      );
    });
  });

  it("renders the 'submitted' badge with submitted_at when already submitted", async () => {
    mockGetStatus.mockResolvedValue({
      submitted: true,
      submitted_at: "2026-05-10T14:30:00",
    });
    await renderPage();

    await waitFor(() => {
      const badge = screen.getByTestId("submission-status-badge");
      expect(badge).toHaveTextContent("monthlyOverride.submitted");
      expect(badge.textContent ?? "").toMatch(/2026-05-10/);
    });
  });

  it("opens WarningModal listing abnormal days when 'submitMonth' is clicked", async () => {
    mockGetStatus.mockResolvedValue({ submitted: false, submitted_at: null });
    await renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("submission-status-badge")).toBeInTheDocument();
    });

    const submitBtn = screen.getByRole("button", {
      name: /monthlyOverride\.submitMonth/,
    });
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    // The single LATE row from the fixture should be listed.
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("2026-05-01");
    expect(dialog).toHaveTextContent("status.late");
    // monthlySubmissionsApi.submit must NOT have been called yet.
    expect(mockSubmit).not.toHaveBeenCalled();
  });

  it("calls monthlySubmissionsApi.submit when 'proceed' is clicked inside the modal", async () => {
    mockGetStatus.mockResolvedValue({ submitted: false, submitted_at: null });
    mockSubmit.mockResolvedValue({
      emp_id: "EMP001",
      year: 2026,
      month: 5,
      submitted_at: "2026-05-14T10:00:00",
    });
    await renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("submission-status-badge")).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: /monthlyOverride\.submitMonth/ }),
      );
    });

    // After modal opens, mockGetStatus may be called again on success — set it to "submitted".
    mockGetStatus.mockResolvedValue({
      submitted: true,
      submitted_at: "2026-05-14T10:00:00",
    });

    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "monthlyOverride.proceed" }),
      );
    });

    await waitFor(() => {
      expect(mockSubmit).toHaveBeenCalledWith("EMP001", 2026, 5);
    });
  });

  it("includes leave_type and remark in the bulk-override PUT body when changed", async () => {
    mockGetStatus.mockResolvedValue({ submitted: false, submitted_at: null });
    await renderPage();

    // Change the leave type on the first editable row via its <select>.
    const selects = screen.getAllByLabelText("monthlyOverride.leaveType");
    await act(async () => {
      fireEvent.change(selects[0], { target: { value: "特休" } });
    });

    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: /monthlyOverride\.save$/ }),
      );
    });

    await waitFor(() => {
      expect(mockPut).toHaveBeenCalled();
    });

    const [url, body] = mockPut.mock.calls[0];
    expect(url).toBe("/api/attendance/override-bulk");
    const typedBody = body as {
      entries: ReadonlyArray<{
        date: string;
        leave_type: string | null;
        remark: string | null;
      }>;
    };
    expect(typedBody.entries).toHaveLength(1);
    expect(typedBody.entries[0]).toMatchObject({
      date: "2026-05-01",
      leave_type: "特休",
      remark: null,
    });
  });
});
