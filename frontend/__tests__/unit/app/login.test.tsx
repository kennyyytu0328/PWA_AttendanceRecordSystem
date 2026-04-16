"use client";

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

import type { TokenResponse } from "@/types";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockPush = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

vi.mock("@/lib/api", () => ({
  apiClient: {
    post: vi.fn(),
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

/** Build a fake JWT with the given payload (no real signature). */
function fakeJwt(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const body = btoa(JSON.stringify(payload));
  const sig = "fake-signature";
  return `${header}.${body}.${sig}`;
}

const TEST_TOKEN = fakeJwt({ sub: "EMP001", role: "EMPLOYEE" });

// ---------------------------------------------------------------------------
// Lazy imports (after mocks are registered)
// ---------------------------------------------------------------------------

async function importAuthContext() {
  return await import("@/lib/auth-context");
}

async function importLoginPage() {
  return await import("@/app/login/page");
}

async function importApi() {
  return await import("@/lib/api");
}

// ---------------------------------------------------------------------------
// Auth Context Tests
// ---------------------------------------------------------------------------

describe("AuthContext", () => {
  beforeEach(() => {
    vi.resetModules();
    localStorage.clear();
    mockPush.mockClear();
  });

  it("provides null user when no token is stored", async () => {
    const { AuthProvider, useAuth } = await importAuthContext();

    function Consumer() {
      const { user, isAuthenticated } = useAuth();
      return (
        <div>
          <span data-testid="user">{user ? user.emp_id : "null"}</span>
          <span data-testid="auth">{String(isAuthenticated)}</span>
        </div>
      );
    }

    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>,
    );

    expect(screen.getByTestId("user").textContent).toBe("null");
    expect(screen.getByTestId("auth").textContent).toBe("false");
  });

  it("restores user from stored token on mount", async () => {
    localStorage.setItem("access_token", TEST_TOKEN);

    const { AuthProvider, useAuth } = await importAuthContext();

    function Consumer() {
      const { user, isAuthenticated } = useAuth();
      return (
        <div>
          <span data-testid="user">{user ? user.emp_id : "null"}</span>
          <span data-testid="role">{user ? user.role : "null"}</span>
          <span data-testid="auth">{String(isAuthenticated)}</span>
        </div>
      );
    }

    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>,
    );

    expect(screen.getByTestId("user").textContent).toBe("EMP001");
    expect(screen.getByTestId("role").textContent).toBe("EMPLOYEE");
    expect(screen.getByTestId("auth").textContent).toBe("true");
  });

  it("login() stores token and updates user", async () => {
    const { AuthProvider, useAuth } = await importAuthContext();
    const { apiClient } = await importApi();

    const mockPost = vi.mocked(apiClient.post);
    mockPost.mockResolvedValueOnce({
      access_token: TEST_TOKEN,
      token_type: "bearer",
    } satisfies TokenResponse);

    let loginFn: (empId: string, password: string) => Promise<void>;

    function Consumer() {
      const { user, login } = useAuth();
      loginFn = login;
      return (
        <span data-testid="user">{user ? user.emp_id : "null"}</span>
      );
    }

    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>,
    );

    expect(screen.getByTestId("user").textContent).toBe("null");

    await waitFor(async () => {
      await loginFn!("EMP001", "password123");
    });

    await waitFor(() => {
      expect(screen.getByTestId("user").textContent).toBe("EMP001");
    });

    expect(localStorage.getItem("access_token")).toBe(TEST_TOKEN);
    expect(mockPost).toHaveBeenCalledWith("/api/auth/login", {
      emp_id: "EMP001",
      password: "password123",
    });
  });

  it("logout() clears token and user", async () => {
    localStorage.setItem("access_token", TEST_TOKEN);

    const { AuthProvider, useAuth } = await importAuthContext();

    let logoutFn: () => void;

    function Consumer() {
      const { user, logout } = useAuth();
      logoutFn = logout;
      return (
        <span data-testid="user">{user ? user.emp_id : "null"}</span>
      );
    }

    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>,
    );

    expect(screen.getByTestId("user").textContent).toBe("EMP001");

    act(() => {
      logoutFn!();
    });

    await waitFor(() => {
      expect(screen.getByTestId("user").textContent).toBe("null");
    });

    expect(localStorage.getItem("access_token")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Login Page Tests
// ---------------------------------------------------------------------------

describe("Login Page", () => {
  beforeEach(() => {
    vi.resetModules();
    localStorage.clear();
    mockPush.mockClear();
  });

  it("renders form fields", async () => {
    const { AuthProvider } = await importAuthContext();
    const { default: LoginPage } = await importLoginPage();

    render(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>,
    );

    expect(
      screen.getByLabelText(/employee id/i),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /sign in|log in|login/i }),
    ).toBeInTheDocument();
  });

  it("shows error on failed login", async () => {
    const { AuthProvider } = await importAuthContext();
    const { default: LoginPage } = await importLoginPage();
    const { apiClient } = await importApi();

    const mockPost = vi.mocked(apiClient.post);
    mockPost.mockRejectedValueOnce(new Error("Invalid credentials"));

    const user = userEvent.setup();

    render(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>,
    );

    await user.type(screen.getByLabelText(/employee id/i), "EMP001");
    await user.type(screen.getByLabelText(/password/i), "wrongpass");
    await user.click(
      screen.getByRole("button", { name: /sign in|log in|login/i }),
    );

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });

    expect(screen.getByRole("alert").textContent).toMatch(
      /invalid credentials/i,
    );
  });
});
