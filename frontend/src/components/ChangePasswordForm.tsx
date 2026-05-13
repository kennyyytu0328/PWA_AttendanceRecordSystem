"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Lock } from "lucide-react";

import { apiClient, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useTranslation } from "@/lib/i18n";
import { changePasswordSchema } from "@/lib/validators";

type FieldErrors = Partial<{
  currentPassword: string;
  newPassword: string;
  confirmPassword: string;
  form: string;
}>;

export function ChangePasswordForm() {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const router = useRouter();

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [submitting, setSubmitting] = useState(false);

  const empId = user?.emp_id ?? "";

  function validate(): { ok: true } | { ok: false; errors: FieldErrors } {
    const result = changePasswordSchema.safeParse({
      currentPassword: current,
      newPassword: next,
      confirmPassword: confirm,
      empId,
    });
    if (result.success) return { ok: true };
    const fieldErrors: FieldErrors = {};
    for (const issue of result.error.issues) {
      const field = issue.path[0];
      const key = `changePassword.errors.${issue.message}`;
      if (field === "currentPassword" && !fieldErrors.currentPassword) {
        fieldErrors.currentPassword = key;
      } else if (field === "newPassword" && !fieldErrors.newPassword) {
        fieldErrors.newPassword = key;
      } else if (field === "confirmPassword" && !fieldErrors.confirmPassword) {
        fieldErrors.confirmPassword = key;
      }
    }
    return { ok: false, errors: fieldErrors };
  }

  const isValid = current.length > 0 && next.length >= 8 && confirm.length > 0;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErrors({});
    const v = validate();
    if (!v.ok) {
      setErrors(v.errors);
      return;
    }
    setSubmitting(true);
    try {
      await apiClient.post("/api/auth/change-password", {
        current_password: current,
        new_password: next,
      });
      logout();
      router.push("/login");
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setErrors({
            currentPassword: "changePassword.errors.wrongCurrent",
          });
        } else if (err.status === 422) {
          const msg = err.detail.toLowerCase();
          if (msg.includes("employee id")) {
            setErrors({ newPassword: "changePassword.errors.sameAsEmpId" });
          } else if (msg.includes("differ")) {
            setErrors({ newPassword: "changePassword.errors.sameAsCurrent" });
          } else if (msg.includes("digit")) {
            setErrors({ newPassword: "changePassword.errors.missingDigit" });
          } else {
            setErrors({ newPassword: "changePassword.errors.tooShort" });
          }
        } else if (err.status === 429) {
          setErrors({ form: "changePassword.errors.rateLimited" });
        } else {
          setErrors({ form: "changePassword.errors.generic" });
        }
      } else {
        setErrors({ form: "changePassword.errors.generic" });
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label
          htmlFor="cp-current"
          className="block text-sm font-medium text-gray-700"
        >
          {t("changePassword.currentLabel")}
        </label>
        <input
          id="cp-current"
          type="password"
          autoComplete="current-password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 shadow-sm focus:border-[#4ec6c1] focus:outline-none"
        />
        {errors.currentPassword && (
          <p className="mt-1 text-sm text-red-600">{t(errors.currentPassword)}</p>
        )}
      </div>

      <div>
        <label
          htmlFor="cp-new"
          className="block text-sm font-medium text-gray-700"
        >
          {t("changePassword.newLabel")}
        </label>
        <input
          id="cp-new"
          type="password"
          autoComplete="new-password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 shadow-sm focus:border-[#4ec6c1] focus:outline-none"
        />
        <p className="mt-1 text-xs text-gray-500">{t("changePassword.hint")}</p>
        {errors.newPassword && (
          <p className="mt-1 text-sm text-red-600">{t(errors.newPassword)}</p>
        )}
      </div>

      <div>
        <label
          htmlFor="cp-confirm"
          className="block text-sm font-medium text-gray-700"
        >
          {t("changePassword.confirmLabel")}
        </label>
        <input
          id="cp-confirm"
          type="password"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 shadow-sm focus:border-[#4ec6c1] focus:outline-none"
        />
        {errors.confirmPassword && (
          <p className="mt-1 text-sm text-red-600">{t(errors.confirmPassword)}</p>
        )}
      </div>

      {errors.form && (
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
        >
          {t(errors.form)}
        </div>
      )}

      <button
        type="submit"
        disabled={!isValid || submitting}
        className="flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-[#4ec6c1] to-[#6dcf7c] px-4 py-2 text-sm font-medium text-white hover:from-[#45b5b0] hover:to-[#5fc06e] disabled:cursor-not-allowed disabled:opacity-50"
      >
        <Lock className="h-4 w-4" />
        {submitting ? t("changePassword.submitting") : t("changePassword.submit")}
      </button>
    </form>
  );
}
