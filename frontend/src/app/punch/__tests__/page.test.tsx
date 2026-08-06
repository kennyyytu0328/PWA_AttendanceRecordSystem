import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Pin to a known weekday (Friday) so the weekend-lock logic never disables
// the punch button and makes this test flaky depending on when it runs.
process.env.TZ = "Asia/Taipei";

// ---------------------------------------------------------------------------
// Mocks (hoisted)
// ---------------------------------------------------------------------------

const stableT = (k: string) => k;
vi.mock("@/lib/i18n", () => ({
  useTranslation: () => ({ t: stableT, locale: "en", setLocale: vi.fn() }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({
    user: { emp_id: "EMP100" },
    isAuthenticated: true,
    isLoading: false,
  }),
}));

const mockPosition = {
  latitude: 24.77,
  longitude: 121.04,
  accuracy: 10,
  error: null,
  loading: false,
};
const mockRequestPosition = vi.fn();
vi.mock("@/hooks/useGeolocation", () => ({
  useGeolocation: () => ({
    position: mockPosition,
    requestPosition: mockRequestPosition,
  }),
}));

vi.mock("@/components/BackButton", () => ({
  BackButton: () => <div data-testid="back-button" />,
}));
vi.mock("@/components/LanguageSwitcher", () => ({
  LanguageSwitcher: () => <div data-testid="lang-switcher" />,
}));

const mockPost = vi.fn();
const mockGet = vi.fn();
vi.mock("@/lib/api", () => ({
  apiClient: {
    post: (...args: unknown[]) => mockPost(...args),
    get: (...args: unknown[]) => mockGet(...args),
  },
}));

import PunchPage from "@/app/punch/page";

/**
 * React attaches the fiber's props (including the original onClick) to the
 * DOM node under a `__reactProps$*` key. Grabbing it lets a test invoke the
 * handler directly, bypassing jsdom's native "no click dispatch on a
 * disabled element" gate. That native gate happens to already block a
 * second `fireEvent.click()` in this environment once React synchronously
 * commits `disabled=true` from the first click — but that's an accident of
 * jsdom's synchronous act() flush, not a guarantee the app relies on (e.g.
 * framer-motion's own tap-gesture dispatch, or any other invocation path,
 * isn't guaranteed to re-check the DOM disabled attribute between two rapid
 * invocations). Calling the handler directly exercises the actual
 * reentrancy guard inside `handlePunch`, independent of DOM gating.
 */
function getOnClick(el: Element): (() => void) | undefined {
  const key = Object.keys(el).find((k) => k.startsWith("__reactProps$"));
  if (!key) return undefined;
  return (el as unknown as Record<string, { onClick?: () => void }>)[key]
    .onClick;
}

const PUNCH_RESULT = {
  work_mode: "OFFICE" as const,
  distance_km: 0.1,
  is_low_accuracy: false,
  log: {},
  tardiness_status: null,
  summary_id: null,
};

/** Routes the shared apiClient.get mock by path. `/api/auth/me` defaults to
 * a profile with no shift_end_time so pre-existing tests (which never set
 * up a late-reason scenario) keep going straight through the direct-submit
 * path, unaffected by the late-leave-reason dialog wiring. */
function mockGetByUrl(
  overrides: {
    readonly authMe?: Record<string, unknown>;
    readonly workdays?: { readonly days: readonly Record<string, unknown>[] };
  } = {},
) {
  mockGet.mockImplementation((url: string) => {
    if (url.startsWith("/api/auth/me")) {
      return Promise.resolve({
        emp_id: "EMP100",
        role: "EMPLOYEE",
        ...overrides.authMe,
      });
    }
    if (url.startsWith("/api/reasons/me")) {
      return Promise.resolve([]);
    }
    if (url.startsWith("/api/config/workdays")) {
      return Promise.resolve(overrides.workdays ?? { days: [] });
    }
    return Promise.resolve({ days: [] });
  });
}

beforeEach(() => {
  // 2026-07-17 is a Friday — well clear of weekend-lock logic.
  vi.setSystemTime(new Date("2026-07-17T09:00:00+08:00"));
  mockPost.mockReset();
  mockGet.mockReset();
  mockRequestPosition.mockReset();
  mockGetByUrl();
  mockPost.mockImplementation(
    () =>
      new Promise((resolve) => {
        setTimeout(() => resolve(PUNCH_RESULT), 50);
      }),
  );
});

describe("PunchPage double-submit lock", () => {
  it("submits one punch per click", async () => {
    render(<PunchPage />);

    fireEvent.click(screen.getByRole("button", { name: /punch/i }));

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    expect(mockPost).toHaveBeenCalledTimes(1);
  });

  it("rapid double-click fires only one POST", async () => {
    render(<PunchPage />);

    const button = screen.getByRole("button", { name: /punch/i });
    const onClick = getOnClick(button);
    expect(onClick).toBeTypeOf("function");

    // Invoke the click handler twice back-to-back within the same act(),
    // simulating a rapid double-tap that fires before any DOM-level
    // disabled gating could intervene between the two invocations.
    act(() => {
      onClick!();
      onClick!();
    });

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    // Flush the pending timeout-based mock resolution (and the resulting
    // setPunchResult/setIsSubmitting state updates) inside act().
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 100));
    });

    expect(mockPost).toHaveBeenCalledTimes(1);
  });
});

describe("PunchPage late-leave reason dialog", () => {
  it("opens the late-reason modal when punching after shift end and sends the reason", async () => {
    mockGetByUrl({ authMe: { shift_end_time: "17:30" } });
    vi.setSystemTime(new Date("2026-07-22T18:31:00")); // Wed after 17:30

    render(<PunchPage />);

    // Let the /api/auth/me fetch resolve and the profile state settle
    // before clicking, so needsLateReason() sees the loaded shift_end_time.
    await act(async () => {
      await Promise.resolve();
    });

    fireEvent.click(screen.getByRole("button", { name: /punch/i }));

    // modal appears instead of immediate submit:
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(mockPost).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /確認|Confirm/ }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith(
        "/api/attendance/punch",
        expect.objectContaining({ late_leave_reason: "PERSONAL" }),
      );
    });
  });

  it("does not open the modal on a weekday national holiday", async () => {
    // 2026-07-22 declared a national holiday by the calendar: punching
    // after shift end must NOT ask for a late reason — there is no shift
    // on a non-working day (#31f), the punch submits directly.
    mockGetByUrl({
      authMe: { shift_end_time: "17:30" },
      workdays: {
        days: [
          {
            date: "2026-07-22",
            weekday_zh: "三",
            is_holiday: true,
            description: "國定假日",
            is_makeup_workday: false,
            day_kind: "NATIONAL_HOLIDAY",
          },
        ],
      },
    });
    vi.setSystemTime(new Date("2026-07-22T18:31:00")); // after 17:30

    render(<PunchPage />);

    // Wait for the calendar probe to overwrite the weekday-guess WORKDAY
    // seed with the authoritative NATIONAL_HOLIDAY before clicking.
    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith(
        expect.stringContaining("/api/config/workdays"),
      ),
    );
    await act(async () => {
      await Promise.resolve();
    });

    fireEvent.click(screen.getByRole("button", { name: /punch/i }));

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mockPost).toHaveBeenCalledWith(
      "/api/attendance/punch",
      expect.not.objectContaining({ late_leave_reason: expect.anything() }),
    );
  });

  it("does not open the modal before shift end", async () => {
    mockGetByUrl({ authMe: { shift_end_time: "17:30" } });
    vi.setSystemTime(new Date("2026-07-22T17:30:00")); // exactly on time

    render(<PunchPage />);

    await act(async () => {
      await Promise.resolve();
    });

    fireEvent.click(screen.getByRole("button", { name: /punch/i }));

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mockPost).toHaveBeenCalledWith(
      "/api/attendance/punch",
      expect.not.objectContaining({ late_leave_reason: expect.anything() }),
    );
  });
});

describe("PunchPage day-kind calendar probe", () => {
  it("keys the calendar lookup by local date, not UTC (Monday morning must not match Sunday)", async () => {
    // Monday 2026-07-20 07:45 local (Asia/Taipei, TZ pinned above). Before
    // 08:00 local, `toISOString().slice(0, 10)` yields the UTC date, which
    // is still Sunday the 19th — a stale UTC-rollback bug (see
    // frontend/src/lib/date.ts) that would match the wrong calendar entry
    // and wrongly lock the button as if today were 例假日.
    vi.setSystemTime(new Date("2026-07-20T07:45:00"));
    mockGetByUrl({
      workdays: {
        days: [
          {
            date: "2026-07-19",
            weekday_zh: "日",
            is_holiday: true,
            description: "例假日",
            is_makeup_workday: false,
            day_kind: "REGULAR_LEAVE",
          },
          {
            date: "2026-07-20",
            weekday_zh: "一",
            is_holiday: false,
            description: "",
            is_makeup_workday: false,
            day_kind: "WORKDAY",
          },
        ],
      },
    });

    render(<PunchPage />);

    // Let the workdays probe resolve and its setTodayKind (if any) commit.
    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith(
        expect.stringContaining("/api/config/workdays"),
      ),
    );
    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByRole("button", { name: /punch/i })).not.toBeDisabled();
    expect(screen.queryByTestId("weekend-lock-notice")).not.toBeInTheDocument();
  });
});
