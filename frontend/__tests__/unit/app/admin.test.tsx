"use client";

import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

import type { Employee, OfficeLocation } from "@/types";

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
const mockPost = vi.fn();
const mockPut = vi.fn();

vi.mock("@/lib/api", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    put: (...args: unknown[]) => mockPut(...args),
    delete: vi.fn(),
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

const EMPLOYEES: readonly Employee[] = [
  {
    emp_id: "EMP001",
    name: "Alice Chen",
    department: "Engineering",
    role: "EMPLOYEE",
    shift_start_time: "09:00",
    shift_end_time: "18:00",
  },
  {
    emp_id: "EMP002",
    name: "Bob Wang",
    department: "Marketing",
    role: "MANAGER",
    shift_start_time: "09:00",
    shift_end_time: "18:00",
  },
] as const;

const OFFICE_LOCATION: OfficeLocation = {
  latitude: 25.033,
  longitude: 121.5654,
};

function mockAuthUser(role: "EMPLOYEE" | "MANAGER" | "HR" | "ADMIN") {
  mockUseAuth.mockReturnValue({
    user: { emp_id: "EMP999", role },
    token: "fake-token",
    login: vi.fn(),
    logout: vi.fn(),
    isAuthenticated: true,
  });
}

// ---------------------------------------------------------------------------
// Lazy import (after mocks are registered)
// ---------------------------------------------------------------------------

async function importAdminPage() {
  return await import("@/app/admin/page");
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("Admin Page", () => {
  beforeEach(() => {
    vi.resetModules();
    mockPush.mockClear();
    mockUseAuth.mockReset();
    mockGet.mockReset();
    mockPost.mockReset();
    mockPut.mockReset();
  });

  it("renders admin panel heading", async () => {
    mockAuthUser("ADMIN");
    mockGet.mockResolvedValue([]);

    const { default: AdminPage } = await importAdminPage();
    render(<AdminPage />);

    expect(
      screen.getByRole("heading", { name: /admin panel/i }),
    ).toBeInTheDocument();
  });

  it("HR user sees employee management section", async () => {
    mockAuthUser("HR");
    mockGet.mockResolvedValue([]);

    const { default: AdminPage } = await importAdminPage();
    render(<AdminPage />);

    expect(
      screen.getByRole("heading", { name: /employee management/i }),
    ).toBeInTheDocument();
  });

  it("HR user sees office location section", async () => {
    mockAuthUser("HR");
    mockGet.mockResolvedValue([]);

    const { default: AdminPage } = await importAdminPage();
    render(<AdminPage />);

    expect(
      screen.getByRole("heading", { name: /office location/i }),
    ).toBeInTheDocument();
  });

  it("ADMIN user sees system config section", async () => {
    mockAuthUser("ADMIN");
    mockGet.mockResolvedValue([]);

    const { default: AdminPage } = await importAdminPage();
    render(<AdminPage />);

    expect(
      screen.getByRole("heading", { name: /system config/i }),
    ).toBeInTheDocument();
  });

  it("EMPLOYEE user sees access denied message", async () => {
    mockAuthUser("EMPLOYEE");

    const { default: AdminPage } = await importAdminPage();
    render(<AdminPage />);

    expect(screen.getByText(/access denied/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: /employee management/i }),
    ).not.toBeInTheDocument();
  });

  it("shows employee list when loaded", async () => {
    mockAuthUser("HR");
    mockGet.mockImplementation((path: string) => {
      if (path.includes("/employees")) {
        return Promise.resolve(EMPLOYEES);
      }
      if (path.includes("/config/office_location")) {
        return Promise.resolve(OFFICE_LOCATION);
      }
      return Promise.resolve([]);
    });

    const { default: AdminPage } = await importAdminPage();
    render(<AdminPage />);

    await waitFor(() => {
      expect(screen.getByText("Alice Chen")).toBeInTheDocument();
    });

    expect(screen.getByText("Bob Wang")).toBeInTheDocument();
    expect(screen.getByText("Engineering")).toBeInTheDocument();
    expect(screen.getByText("Marketing")).toBeInTheDocument();
  });

  it("shows office location form", async () => {
    mockAuthUser("HR");
    mockGet.mockImplementation((path: string) => {
      if (path.includes("/employees")) {
        return Promise.resolve([]);
      }
      if (path.includes("/config/office_location")) {
        return Promise.resolve(OFFICE_LOCATION);
      }
      return Promise.resolve([]);
    });

    const { default: AdminPage } = await importAdminPage();
    render(<AdminPage />);

    await waitFor(() => {
      expect(screen.getByLabelText(/latitude/i)).toBeInTheDocument();
    });

    expect(screen.getByLabelText(/longitude/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /update location/i }),
    ).toBeInTheDocument();
  });
});
