import { describe, expect, it } from "vitest";

import { changePasswordSchema } from "@/lib/validators";

describe("changePasswordSchema", () => {
  const valid = {
    currentPassword: "oldPass1",
    newPassword: "newPass1",
    confirmPassword: "newPass1",
    empId: "EMP001",
  };

  it("accepts a valid payload", () => {
    expect(changePasswordSchema.safeParse(valid).success).toBe(true);
  });

  it("rejects when current password is empty", () => {
    const r = changePasswordSchema.safeParse({ ...valid, currentPassword: "" });
    expect(r.success).toBe(false);
  });

  it("rejects when new password is too short", () => {
    const r = changePasswordSchema.safeParse({
      ...valid,
      newPassword: "short1",
      confirmPassword: "short1",
    });
    expect(r.success).toBe(false);
    if (!r.success) {
      expect(JSON.stringify(r.error.issues)).toContain("tooShort");
    }
  });

  it("rejects when new password has no digit", () => {
    const r = changePasswordSchema.safeParse({
      ...valid,
      newPassword: "abcdefgh",
      confirmPassword: "abcdefgh",
    });
    expect(r.success).toBe(false);
    if (!r.success) {
      expect(JSON.stringify(r.error.issues)).toContain("missingDigit");
    }
  });

  it("rejects when confirm doesn't match new", () => {
    const r = changePasswordSchema.safeParse({
      ...valid,
      confirmPassword: "different1",
    });
    expect(r.success).toBe(false);
    if (!r.success) {
      expect(JSON.stringify(r.error.issues)).toContain("mismatch");
    }
  });

  it("rejects when new password equals current password", () => {
    const r = changePasswordSchema.safeParse({
      ...valid,
      newPassword: "oldPass1",
      confirmPassword: "oldPass1",
    });
    expect(r.success).toBe(false);
    if (!r.success) {
      expect(JSON.stringify(r.error.issues)).toContain("sameAsCurrent");
    }
  });

  it("rejects when new password equals emp_id", () => {
    const r = changePasswordSchema.safeParse({
      ...valid,
      newPassword: "EMP001",
      confirmPassword: "EMP001",
    });
    expect(r.success).toBe(false);
    if (!r.success) {
      expect(JSON.stringify(r.error.issues)).toContain("sameAsEmpId");
    }
  });
});
