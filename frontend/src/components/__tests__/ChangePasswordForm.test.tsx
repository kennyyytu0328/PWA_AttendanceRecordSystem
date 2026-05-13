import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { ChangePasswordForm } from "@/components/ChangePasswordForm";

// Minimal mocks for the hooks/router/api the component depends on.
const mockPush = vi.fn();
const mockLogout = vi.fn();
const mockPost = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({
    user: { emp_id: "EMP001", role: "EMPLOYEE" },
    logout: mockLogout,
  }),
}));

vi.mock("@/lib/api", () => ({
  apiClient: { post: (...args: unknown[]) => mockPost(...args) },
  ApiError: class ApiError extends Error {
    constructor(public status: number, public detail: string) {
      super(detail);
    }
  },
}));

// Translation just echoes the key so we can assert on keys.
vi.mock("@/lib/i18n", () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));

beforeEach(() => {
  mockPush.mockReset();
  mockLogout.mockReset();
  mockPost.mockReset();
});

describe("ChangePasswordForm", () => {
  function fill(current: string, next: string, confirm: string) {
    fireEvent.change(screen.getByLabelText("changePassword.currentLabel"), {
      target: { value: current },
    });
    fireEvent.change(screen.getByLabelText("changePassword.newLabel"), {
      target: { value: next },
    });
    fireEvent.change(screen.getByLabelText("changePassword.confirmLabel"), {
      target: { value: confirm },
    });
  }

  it("disables submit until form is valid", () => {
    render(<ChangePasswordForm />);
    expect(
      screen.getByRole("button", { name: "changePassword.submit" }),
    ).toBeDisabled();
  });

  it("blocks submit when new password lacks a digit", async () => {
    render(<ChangePasswordForm />);
    fill("oldPass1", "abcdefgh", "abcdefgh");
    fireEvent.click(screen.getByRole("button", { name: "changePassword.submit" }));
    await screen.findByText("changePassword.errors.missingDigit");
    expect(mockPost).not.toHaveBeenCalled();
  });

  it("blocks submit when confirm doesn't match", async () => {
    render(<ChangePasswordForm />);
    fill("oldPass1", "newPass1", "different1");
    fireEvent.click(screen.getByRole("button", { name: "changePassword.submit" }));
    await screen.findByText("changePassword.errors.mismatch");
    expect(mockPost).not.toHaveBeenCalled();
  });

  it("on 200, logs out and redirects to /login", async () => {
    mockPost.mockResolvedValueOnce({ message: "ok" });
    render(<ChangePasswordForm />);
    fill("oldPass1", "newPass1", "newPass1");
    fireEvent.click(screen.getByRole("button", { name: "changePassword.submit" }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/api/auth/change-password", {
        current_password: "oldPass1",
        new_password: "newPass1",
      });
    });
    await waitFor(() => expect(mockLogout).toHaveBeenCalled());
    expect(mockPush).toHaveBeenCalledWith("/login");
  });

  it("on 401, shows wrongCurrent error", async () => {
    const { ApiError } = await import("@/lib/api");
    mockPost.mockRejectedValueOnce(new ApiError(401, "Invalid credentials"));
    render(<ChangePasswordForm />);
    fill("WRONG_PWD1", "newPass1", "newPass1");
    fireEvent.click(screen.getByRole("button", { name: "changePassword.submit" }));
    await screen.findByText("changePassword.errors.wrongCurrent");
  });

  it("on 422 about emp_id, shows sameAsEmpId error", async () => {
    const { ApiError } = await import("@/lib/api");
    mockPost.mockRejectedValueOnce(
      new ApiError(422, "new password must not equal employee ID"),
    );
    render(<ChangePasswordForm />);
    // Pass a value that survives client-side validation: 8+ chars + digit and
    // not literally equal to "EMP001" (client check is strict equality).
    fill("oldPass1", "EMP001x1", "EMP001x1");
    fireEvent.click(screen.getByRole("button", { name: "changePassword.submit" }));
    await screen.findByText("changePassword.errors.sameAsEmpId");
  });

  it("on 429, shows rate-limit error", async () => {
    const { ApiError } = await import("@/lib/api");
    mockPost.mockRejectedValueOnce(new ApiError(429, "too many"));
    render(<ChangePasswordForm />);
    fill("oldPass1", "newPass1", "newPass1");
    fireEvent.click(screen.getByRole("button", { name: "changePassword.submit" }));
    await screen.findByText("changePassword.errors.rateLimited");
  });
});
