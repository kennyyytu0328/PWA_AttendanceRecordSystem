import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Employee, Role } from "@/types";

// ---------------------------------------------------------------------------
// Mocks (hoisted)
// ---------------------------------------------------------------------------

const authState: { user: { emp_id: string; role: Role } } = {
  user: { emp_id: "ADM001", role: "ADMIN" },
};

const stableT = (k: string, params?: Record<string, string | number>) => {
  if (!params) return k;
  return Object.entries(params).reduce<string>(
    (acc, [pk, pv]) => acc.replace(`{${pk}}`, String(pv)),
    k,
  );
};
const stableSetLocale = vi.fn();
const stableI18n = { t: stableT, locale: "en" as const, setLocale: stableSetLocale };

vi.mock("@/lib/i18n", () => ({
  useTranslation: () => stableI18n,
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
const mockPut = vi.fn();
const mockDelete = vi.fn();

vi.mock("@/lib/api", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    put: (...args: unknown[]) => mockPut(...args),
    delete: (...args: unknown[]) => mockDelete(...args),
  },
}));

const mockLeaveTypesList = vi.fn();
const mockLeaveTypesUpdate = vi.fn();

vi.mock("@/lib/api/leave-types", () => ({
  leaveTypesApi: {
    list: (...args: unknown[]) => mockLeaveTypesList(...args),
    update: (...args: unknown[]) => mockLeaveTypesUpdate(...args),
  },
}));

// Imports after mocks
import AdminPage from "@/app/admin/page";
import { LeaveTypesTab } from "@/components/admin/LeaveTypesTab";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeEmployee(overrides: Partial<Employee> = {}): Employee {
  return {
    emp_id: "EMP001",
    name: "Alice",
    department: "ENG",
    role: "EMPLOYEE",
    shift_start_time: "09:00",
    shift_end_time: "18:00",
    terminated_at: null,
    ...overrides,
  };
}

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
  mockPut.mockReset();
  mockDelete.mockReset();
  mockLeaveTypesList.mockReset();
  mockLeaveTypesUpdate.mockReset();
  authState.user = { emp_id: "ADM001", role: "ADMIN" };

  // Default api responses for admin page
  mockGet.mockImplementation((url: string) => {
    if (url === "/api/config/departments") return Promise.resolve({ departments: ["ENG"] });
    if (url.startsWith("/api/employees")) return Promise.resolve([makeEmployee()]);
    if (url === "/api/config/office-location") return Promise.resolve({ key: "office_location", value: null });
    if (url === "/api/config/grace-period") return Promise.resolve({ minutes: 5 });
    if (url === "/api/config") return Promise.resolve([]);
    if (url === "/api/config/workdays/status") return Promise.resolve({ calendars: [] });
    return Promise.resolve({});
  });
  mockLeaveTypesList.mockResolvedValue({ leave_types: ["年假", "病假"] });
  mockLeaveTypesUpdate.mockImplementation((types: string[]) =>
    Promise.resolve({ leave_types: types }),
  );
});

// ---------------------------------------------------------------------------
// Tests: ADMIN-only Delete button
// ---------------------------------------------------------------------------

describe("AdminPage employee delete button", () => {
  it("renders Delete button when user is ADMIN", async () => {
    authState.user = { emp_id: "ADM001", role: "ADMIN" };
    render(<AdminPage />);

    await waitFor(() => {
      expect(screen.getByText("EMP001")).toBeInTheDocument();
    });

    // Delete button uses title="admin.deleteEmployee"
    expect(screen.getByTitle("admin.deleteEmployee")).toBeInTheDocument();
    // Terminate also present
    expect(screen.getByTitle("admin.terminateEmployee")).toBeInTheDocument();
  });

  it("hides Delete button when user is HR (only Terminate visible)", async () => {
    authState.user = { emp_id: "HR001", role: "HR" };
    render(<AdminPage />);

    await waitFor(() => {
      expect(screen.getByText("EMP001")).toBeInTheDocument();
    });

    expect(screen.queryByTitle("admin.deleteEmployee")).not.toBeInTheDocument();
    expect(screen.getByTitle("admin.terminateEmployee")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Tests: LeaveTypesTab
// ---------------------------------------------------------------------------

describe("LeaveTypesTab", () => {
  it("loads and lists leave types from leaveTypesApi.list", async () => {
    render(<LeaveTypesTab />);

    await waitFor(() => {
      expect(mockLeaveTypesList).toHaveBeenCalledTimes(1);
    });
    expect(await screen.findByText("年假")).toBeInTheDocument();
    expect(screen.getByText("病假")).toBeInTheDocument();
  });

  it("adds a new type and calls update with merged array on save", async () => {
    render(<LeaveTypesTab />);
    await screen.findByText("年假");

    const input = screen.getByPlaceholderText("admin.leaveTypesPlaceholder");
    fireEvent.change(input, { target: { value: "事假" } });
    fireEvent.click(screen.getByTestId("leave-types-add-button"));

    expect(await screen.findByText("事假")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("leave-types-save-button"));

    await waitFor(() => {
      expect(mockLeaveTypesUpdate).toHaveBeenCalledWith(["年假", "病假", "事假"]);
    });
  });

  it("removes a type and calls update with filtered array on save", async () => {
    render(<LeaveTypesTab />);
    await screen.findByText("年假");

    const removeButton = screen.getByTestId("leave-types-remove-病假");
    fireEvent.click(removeButton);

    await waitFor(() => {
      expect(screen.queryByText("病假")).not.toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("leave-types-save-button"));

    await waitFor(() => {
      expect(mockLeaveTypesUpdate).toHaveBeenCalledWith(["年假"]);
    });
  });
});
