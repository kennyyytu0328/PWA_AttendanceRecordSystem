"use client";

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

import type { PunchResponse } from "@/types";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockPush = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

const mockRequestPosition = vi.fn();
const mockUseGeolocation = vi.fn();

vi.mock("@/hooks/useGeolocation", () => ({
  useGeolocation: (...args: unknown[]) => mockUseGeolocation(...args),
}));

const mockUseAuth = vi.fn();

vi.mock("@/lib/auth-context", () => ({
  useAuth: (...args: unknown[]) => mockUseAuth(...args),
}));

vi.mock("@/lib/api", () => ({
  apiClient: {
    post: vi.fn(),
    get: vi.fn(),
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

function defaultGeolocationState() {
  return {
    position: {
      latitude: null,
      longitude: null,
      accuracy: null,
      error: null,
      loading: false,
    },
    requestPosition: mockRequestPosition,
  };
}

function authenticatedUser() {
  return {
    user: { emp_id: "EMP001", role: "EMPLOYEE" as const },
    token: "fake-token",
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
  };
}

// ---------------------------------------------------------------------------
// Lazy imports (after mocks are registered)
// ---------------------------------------------------------------------------

async function importPunchPage() {
  return await import("@/app/punch/page");
}

async function importApi() {
  return await import("@/lib/api");
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("Punch Page", () => {
  beforeEach(() => {
    vi.resetModules();
    mockPush.mockClear();
    mockRequestPosition.mockClear();
    mockUseGeolocation.mockReturnValue(defaultGeolocationState());
    mockUseAuth.mockReturnValue(authenticatedUser());
  });

  it("renders punch button", async () => {
    const { default: PunchPage } = await importPunchPage();

    render(<PunchPage />);

    expect(
      screen.getByRole("button", { name: /punch/i }),
    ).toBeInTheDocument();
  });

  it("shows loading state when punching", async () => {
    // Simulate geolocation loading
    mockUseGeolocation.mockReturnValue({
      position: {
        latitude: null,
        longitude: null,
        accuracy: null,
        error: null,
        loading: true,
      },
      requestPosition: mockRequestPosition,
    });

    const { default: PunchPage } = await importPunchPage();

    render(<PunchPage />);

    const button = screen.getByRole("button", { name: /punch|processing/i });
    expect(button).toBeDisabled();
  });

  it("displays punch result (work mode, distance) on success", async () => {
    const { default: PunchPage } = await importPunchPage();
    const { apiClient } = await importApi();

    const mockPost = vi.mocked(apiClient.post);
    const punchResult: PunchResponse = {
      work_mode: "WFO",
      distance_km: 0.05,
      is_low_accuracy: false,
    };
    mockPost.mockResolvedValueOnce(punchResult);

    // Geolocation resolves immediately
    mockUseGeolocation.mockReturnValue({
      position: {
        latitude: 25.033,
        longitude: 121.565,
        accuracy: 10,
        error: null,
        loading: false,
      },
      requestPosition: mockRequestPosition,
    });

    const user = userEvent.setup();
    render(<PunchPage />);

    await user.click(screen.getByRole("button", { name: /punch/i }));

    await waitFor(() => {
      expect(screen.getByText(/WFO/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/0\.05/)).toBeInTheDocument();
  });

  it("shows error when geolocation fails", async () => {
    mockUseGeolocation.mockReturnValue({
      position: {
        latitude: null,
        longitude: null,
        accuracy: null,
        error: "Location permission denied. Please enable location access in your browser settings.",
        loading: false,
      },
      requestPosition: mockRequestPosition,
    });

    const { default: PunchPage } = await importPunchPage();

    render(<PunchPage />);

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("alert").textContent).toMatch(
      /location permission denied/i,
    );
  });

  it("shows error when API call fails", async () => {
    const { default: PunchPage } = await importPunchPage();
    const { apiClient } = await importApi();

    const mockPost = vi.mocked(apiClient.post);
    mockPost.mockRejectedValueOnce(new Error("Server error"));

    mockUseGeolocation.mockReturnValue({
      position: {
        latitude: 25.033,
        longitude: 121.565,
        accuracy: 10,
        error: null,
        loading: false,
      },
      requestPosition: mockRequestPosition,
    });

    const user = userEvent.setup();
    render(<PunchPage />);

    await user.click(screen.getByRole("button", { name: /punch/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });

    expect(screen.getByRole("alert").textContent).toMatch(/server error/i);
  });

  it("redirects to login when not authenticated", async () => {
    mockUseAuth.mockReturnValue({
      user: null,
      token: null,
      isAuthenticated: false,
      login: vi.fn(),
      logout: vi.fn(),
    });

    const { default: PunchPage } = await importPunchPage();

    render(<PunchPage />);

    expect(mockPush).toHaveBeenCalledWith("/login");
  });

  it("shows low accuracy warning when applicable", async () => {
    const { default: PunchPage } = await importPunchPage();
    const { apiClient } = await importApi();

    const mockPost = vi.mocked(apiClient.post);
    const punchResult: PunchResponse = {
      work_mode: "WFH",
      distance_km: 2.5,
      is_low_accuracy: true,
    };
    mockPost.mockResolvedValueOnce(punchResult);

    mockUseGeolocation.mockReturnValue({
      position: {
        latitude: 25.033,
        longitude: 121.565,
        accuracy: 500,
        error: null,
        loading: false,
      },
      requestPosition: mockRequestPosition,
    });

    const user = userEvent.setup();
    render(<PunchPage />);

    await user.click(screen.getByRole("button", { name: /punch/i }));

    await waitFor(() => {
      expect(screen.getByText(/low accuracy/i)).toBeInTheDocument();
    });
  });

  it("disables button while loading", async () => {
    mockUseGeolocation.mockReturnValue({
      position: {
        latitude: null,
        longitude: null,
        accuracy: null,
        error: null,
        loading: true,
      },
      requestPosition: mockRequestPosition,
    });

    const { default: PunchPage } = await importPunchPage();

    render(<PunchPage />);

    const button = screen.getByRole("button", { name: /punch|processing/i });
    expect(button).toBeDisabled();
  });
});
