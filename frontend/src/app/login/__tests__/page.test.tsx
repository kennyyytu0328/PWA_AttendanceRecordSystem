import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------
const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

const mockLogin = vi.fn();
const mockLoginWithToken = vi.fn();
vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({ login: mockLogin, loginWithToken: mockLoginWithToken }),
}));

const mockAuthenticate = vi.fn();
vi.mock("@/hooks/useWebAuthn", () => ({
  useWebAuthn: () => ({
    state: { isSupported: false, loading: false, error: null },
    authenticate: mockAuthenticate,
  }),
}));

import LoginPage from "@/app/login/page";

describe("LoginPage — remembers the last employee ID", () => {
  beforeEach(() => {
    localStorage.clear();
    mockPush.mockReset();
    mockLogin.mockReset();
    mockLoginWithToken.mockReset();
    mockAuthenticate.mockReset();
  });

  it("prefills the employee ID input from storage on mount", async () => {
    localStorage.setItem("last_emp_id", "EMP777");

    render(<LoginPage />);

    const input = screen.getByLabelText("Employee ID") as HTMLInputElement;
    await waitFor(() => expect(input.value).toBe("EMP777"));
  });

  it("leaves the input empty when nothing was stored", () => {
    render(<LoginPage />);

    const input = screen.getByLabelText("Employee ID") as HTMLInputElement;
    expect(input.value).toBe("");
  });

  it("saves the employee ID after a successful password login", async () => {
    mockLogin.mockResolvedValueOnce(undefined);

    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText("Employee ID"), {
      target: { value: "EMP555" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "pass1234" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() =>
      expect(mockLogin).toHaveBeenCalledWith("EMP555", "pass1234"),
    );
    expect(localStorage.getItem("last_emp_id")).toBe("EMP555");
  });

  it("does not save the employee ID when login fails", async () => {
    mockLogin.mockRejectedValueOnce(new Error("Invalid credentials"));

    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText("Employee ID"), {
      target: { value: "EMP000" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "wrongpass" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(mockLogin).toHaveBeenCalled());
    expect(localStorage.getItem("last_emp_id")).toBeNull();
  });
});
