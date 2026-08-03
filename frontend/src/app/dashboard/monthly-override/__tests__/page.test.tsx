import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import MonthlyOverridePage from "@/app/dashboard/monthly-override/page";
import { ApiError } from "@/lib/api";

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

const mockUseAuth = vi.fn();
vi.mock("@/lib/auth-context", () => ({
  useAuth: () => mockUseAuth(),
}));
mockUseAuth.mockReturnValue({
  user: { emp_id: "EMP001", role: "EMPLOYEE" },
  token: "tok",
  isAuthenticated: true,
  isLoading: false,
  login: vi.fn(),
  loginWithToken: vi.fn(),
  logout: vi.fn(),
});

vi.mock("@/components/BackButton", () => ({
  BackButton: () => <div data-testid="back-button" />,
}));

vi.mock("@/components/LanguageSwitcher", () => ({
  LanguageSwitcher: () => <div data-testid="lang-switcher" />,
}));

const mockGet = vi.fn();
const mockPut = vi.fn();
const mockPost = vi.fn();

// Keep the real ApiError class export (the page does `err instanceof
// ApiError`) while overriding apiClient with test doubles.
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    apiClient: {
      get: (...args: unknown[]) => mockGet(...args),
      put: (...args: unknown[]) => mockPut(...args),
      post: (...args: unknown[]) => mockPost(...args),
    },
  };
});

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

const mockOverrideLockGet = vi.fn();
const mockOverrideLockSet = vi.fn();
vi.mock("@/lib/api/override-lock", () => ({
  overrideLockApi: {
    get: (...args: unknown[]) => mockOverrideLockGet(...args),
    set: (...args: unknown[]) => mockOverrideLockSet(...args),
  },
}));
// Default: unlocked, so pre-existing tests (which never touch the lock)
// keep behaving exactly as before.
mockOverrideLockGet.mockResolvedValue({ locked: false });

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
    day_kind?: string;
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
  late_leave_reason?: string | null;
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
      late_leave_reason: "PERSONAL",
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
      late_leave_reason: null,
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

  it("renders the late-leave reason column, prefills it, and saves changes", async () => {
    mockGetStatus.mockResolvedValue({ submitted: false, submitted_at: null });
    await renderPage();

    const selects = await screen.findAllByTestId("late-reason-select");
    expect(selects.length).toBeGreaterThan(0);

    // Prefilled from the API fixture: 2026-05-01 has late_leave_reason "PERSONAL".
    expect((selects[0] as HTMLSelectElement).value).toBe("PERSONAL");

    await act(async () => {
      fireEvent.change(selects[0], { target: { value: "ASSIGNED_OVERTIME" } });
    });

    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: /monthlyOverride\.save$/ }),
      );
    });

    await waitFor(() => {
      expect(mockPut).toHaveBeenCalledWith(
        "/api/attendance/override-bulk",
        expect.objectContaining({
          entries: expect.arrayContaining([
            expect.objectContaining({ late_leave_reason: "ASSIGNED_OVERTIME" }),
          ]),
        }),
      );
    });
  });
});

describe("MonthlyOverridePage late-leave reason hard-block", () => {
  // The page's year/month state defaults to the real current date (it isn't
  // driven by the mocked workdays response's own year/month fields), so the
  // fixture date must track "today" rather than a hardcoded month — otherwise
  // the mockSubmit(empId, year, month) assertion drifts as time passes.
  const now = new Date();
  const LR_YEAR = now.getFullYear();
  const LR_MONTH = now.getMonth() + 1;
  const LR_DATE = `${LR_YEAR}-${String(LR_MONTH).padStart(2, "0")}-22`;

  function buildLateReasonWorkdays(): WorkdayResp {
    return {
      year: LR_YEAR,
      month: LR_MONTH,
      days: [
        {
          date: LR_DATE,
          weekday_zh: "週三",
          is_holiday: false,
          description: "",
          is_makeup_workday: false,
          // Explicit so the row is treated as a workday regardless of which
          // real weekday day-22 falls on this month.
          day_kind: "WORKDAY",
        },
      ],
    };
  }

  function wireLateReasonApi(lateLeaveReason: string | null): void {
    mockGet.mockImplementation((url: string) => {
      if (url.startsWith("/api/config/workdays")) {
        return Promise.resolve(buildLateReasonWorkdays());
      }
      if (url.startsWith("/api/attendance/summaries")) {
        return Promise.resolve([
          {
            id: 1,
            emp_id: "EMP001",
            date: LR_DATE,
            first_clock_in: `${LR_DATE}T09:00:00`,
            last_clock_out: `${LR_DATE}T19:00:00`,
            status: "NORMAL",
            leave_type: null,
            remark: null,
            late_leave_reason: lateLeaveReason,
          },
        ]);
      }
      if (url.startsWith("/api/employees")) {
        return Promise.resolve([]);
      }
      if (url.startsWith("/api/auth/me")) {
        return Promise.resolve({
          emp_id: "EMP001",
          role: "EMPLOYEE",
          shift_start_time: "09:00",
          shift_end_time: "18:00",
        });
      }
      if (url.startsWith("/api/config/late-reason-leave-types")) {
        return Promise.resolve({ leave_types: ["出差"] });
      }
      return Promise.reject(new Error(`unmocked get: ${url}`));
    });
    mockPut.mockResolvedValue({ emp_id: "EMP001", updated_count: 1, results: [] });
    mockListLeaveTypes.mockResolvedValue({ leave_types: ["特休", "病假", "事假"] });
    mockGetStatus.mockResolvedValue({ submitted: false, submitted_at: null });
  }

  async function renderLateReasonPage(): Promise<void> {
    await act(async () => {
      render(<MonthlyOverridePage />);
    });
    await waitFor(() => {
      expect(screen.getByText(LR_DATE)).toBeInTheDocument();
    });
  }

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("hard-blocks 本月送單 when a required late-leave reason is missing", async () => {
    wireLateReasonApi(null);
    await renderLateReasonPage();

    const submitBtn = await screen.findByRole("button", {
      name: /monthlyOverride\.submitMonth/,
    });
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveTextContent(LR_DATE);
    expect(mockSubmit).not.toHaveBeenCalled();
  });

  it("allows 本月送單 when reasons are filled or day is exempt", async () => {
    wireLateReasonApi("PERSONAL");
    mockSubmit.mockResolvedValue({
      emp_id: "EMP001",
      year: LR_YEAR,
      month: LR_MONTH,
      submitted_at: `${LR_DATE}T20:00:00`,
    });
    await renderLateReasonPage();

    const submitBtn = await screen.findByRole("button", {
      name: /monthlyOverride\.submitMonth/,
    });
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    await waitFor(() => {
      expect(mockSubmit).toHaveBeenCalledWith("EMP001", LR_YEAR, LR_MONTH);
    });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("opens the missing-reason modal from the backend's 400 dates when the local rule misses it (seconds-precision gap)", async () => {
    // Clock-out carries seconds (":45") the frontend's extractTime() drops,
    // so the minute-truncated clockOut ("18:00") equals shift end and the
    // local rule finds nothing — but the backend compares at full precision
    // and still rejects. The submit call must reach the API (no local block)
    // and the 400's structured `dates` must drive the modal.
    mockGet.mockImplementation((url: string) => {
      if (url.startsWith("/api/config/workdays")) {
        return Promise.resolve(buildLateReasonWorkdays());
      }
      if (url.startsWith("/api/attendance/summaries")) {
        return Promise.resolve([
          {
            id: 1,
            emp_id: "EMP001",
            date: LR_DATE,
            first_clock_in: `${LR_DATE}T09:00:00`,
            last_clock_out: `${LR_DATE}T18:00:45`,
            status: "NORMAL",
            leave_type: null,
            remark: null,
            late_leave_reason: null,
          },
        ]);
      }
      if (url.startsWith("/api/employees")) {
        return Promise.resolve([]);
      }
      if (url.startsWith("/api/auth/me")) {
        return Promise.resolve({
          emp_id: "EMP001",
          role: "EMPLOYEE",
          shift_start_time: "09:00",
          shift_end_time: "18:00",
        });
      }
      if (url.startsWith("/api/config/late-reason-leave-types")) {
        return Promise.resolve({ leave_types: ["出差"] });
      }
      return Promise.reject(new Error(`unmocked get: ${url}`));
    });
    mockPut.mockResolvedValue({ emp_id: "EMP001", updated_count: 1, results: [] });
    mockListLeaveTypes.mockResolvedValue({ leave_types: ["特休", "病假", "事假"] });
    mockGetStatus.mockResolvedValue({ submitted: false, submitted_at: null });
    mockSubmit.mockRejectedValue(
      new ApiError(400, "延後下班原因未填寫完成，無法送單", "late_reason_missing", {
        code: "late_reason_missing",
        message: "延後下班原因未填寫完成，無法送單",
        dates: [LR_DATE],
      }),
    );

    await renderLateReasonPage();

    const submitBtn = await screen.findByRole("button", {
      name: /monthlyOverride\.submitMonth/,
    });
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    // Local gate let it through — the API was actually called.
    await waitFor(() => {
      expect(mockSubmit).toHaveBeenCalledWith("EMP001", LR_YEAR, LR_MONTH);
    });

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent(LR_DATE);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("MonthlyOverridePage single-punch display", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    wireApi();
    mockGetStatus.mockResolvedValue({ submitted: false, submitted_at: null });
  });

  it("blanks the clock-out when clock-in === clock-out (single punch), keeping the time in clock-in", async () => {
    // A single physical punch is stored as first_clock_in === last_clock_out.
    // The echoed clock-out is misleading ("clocked in, never clocked out"), so
    // it must render blank while clock-in keeps the time.
    mockGet.mockImplementation((url: string) => {
      if (url.startsWith("/api/config/workdays")) {
        return Promise.resolve(buildWorkdays());
      }
      if (url.startsWith("/api/attendance/summaries")) {
        return Promise.resolve([
          {
            id: 10,
            emp_id: "EMP001",
            date: "2026-05-01",
            first_clock_in: "2026-05-01T09:44:19",
            last_clock_out: "2026-05-01T09:44:19",
            status: "LATE",
            leave_type: null,
            remark: null,
          },
        ]);
      }
      if (url.startsWith("/api/employees")) {
        return Promise.resolve([]);
      }
      return Promise.reject(new Error(`unmocked get: ${url}`));
    });
    await renderPage();

    expect(screen.getAllByTestId("clock-in-input")[0]).toHaveValue("09:44");
    expect(screen.getAllByTestId("clock-out-input")[0]).toHaveValue("");
  });
});

describe("MonthlyOverridePage overtime punch-time validation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    wireApi();
    mockGetStatus.mockResolvedValue({ submitted: false, submitted_at: null });
  });

  it("blocks save and shows a modal when overtime is set without complete punch times", async () => {
    await renderPage();

    // 2026-05-01 is the first editable row and has both punch times.
    // Clear its clock-out, then set overtime → invalid (overtime needs both punches).
    await act(async () => {
      fireEvent.change(screen.getAllByTestId("clock-out-input")[0], {
        target: { value: "" },
      });
    });
    await act(async () => {
      fireEvent.change(screen.getAllByTestId("overtime-select")[0], {
        target: { value: "2" },
      });
    });

    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: /monthlyOverride\.save$/ }),
      );
    });

    // A blocking modal lists the offending date; the PUT is never sent.
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("2026-05-01");
    expect(mockPut).not.toHaveBeenCalled();
  });

  it("allows save when overtime is set and both punch times are present", async () => {
    await renderPage();

    // 2026-05-01 already has clock-in 09:30 and clock-out 18:00 → setting overtime is valid.
    await act(async () => {
      fireEvent.change(screen.getAllByTestId("overtime-select")[0], {
        target: { value: "2" },
      });
    });

    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: /monthlyOverride\.save$/ }),
      );
    });

    await waitFor(() => {
      expect(mockPut).toHaveBeenCalled();
    });

    const [, body] = mockPut.mock.calls[0];
    const typedBody = body as {
      entries: ReadonlyArray<{ date: string; overtime_hours: number | null }>;
    };
    expect(typedBody.entries[0]).toMatchObject({
      date: "2026-05-01",
      overtime_hours: 2,
    });
  });
});

describe("MonthlyOverridePage month-end override lock", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    wireApi();
    mockGetStatus.mockResolvedValue({ submitted: false, submitted_at: null });
    mockUseAuth.mockReturnValue({
      user: { emp_id: "EMP001", role: "EMPLOYEE" },
      token: "tok",
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      loginWithToken: vi.fn(),
      logout: vi.fn(),
    });
    mockOverrideLockGet.mockResolvedValue({ locked: true });
  });

  it("locks the page for employees when override lock is on", async () => {
    await renderPage();

    expect(
      await screen.findByTestId("override-lock-banner"),
    ).toBeInTheDocument();
    expect(screen.queryAllByTestId("clock-in-input")).toHaveLength(0);
    expect(
      screen.getByRole("button", { name: /monthlyOverride\.submitMonth/ }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: /monthlyOverride\.save$/ }),
    ).toBeDisabled();
  });

  it("does not lock the page for HR when override lock is on", async () => {
    mockUseAuth.mockReturnValue({
      user: { emp_id: "HR001", role: "HR" },
      token: "tok",
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      loginWithToken: vi.fn(),
      logout: vi.fn(),
    });
    await renderPage();

    await waitFor(() => {
      expect(mockOverrideLockGet).toHaveBeenCalled();
    });
    expect(screen.queryByTestId("override-lock-banner")).not.toBeInTheDocument();
    expect(screen.getAllByTestId("clock-in-input").length).toBeGreaterThan(0);
  });
});
