"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";
import { Fingerprint } from "lucide-react";

import { useAuth } from "@/lib/auth-context";
import { useTranslation } from "@/lib/i18n";
import { useWebAuthn } from "@/hooks/useWebAuthn";
import { loginRequestSchema } from "@/lib/validators";
import { getLastEmpId, saveLastEmpId } from "@/lib/lastEmpId";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";

export default function LoginPage() {
  const router = useRouter();
  const { login, loginWithToken } = useAuth();
  const { t } = useTranslation();
  const { state: webauthnState, authenticate } = useWebAuthn();

  const [empId, setEmpId] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isFingerprintLoading, setIsFingerprintLoading] = useState(false);

  // Prefill the employee ID used for the last successful login (client only).
  useEffect(() => {
    const lastEmpId = getLastEmpId();
    if (lastEmpId) {
      setEmpId(lastEmpId);
    }
  }, []);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);

    const result = loginRequestSchema.safeParse({
      emp_id: empId,
      password,
    });

    if (!result.success) {
      const firstIssue = result.error.issues[0];
      setError(firstIssue?.message ?? t("login.validationFailed"));
      return;
    }

    setIsSubmitting(true);
    try {
      await login(empId, password);
      saveLastEmpId(empId);
      router.push("/dashboard");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : t("login.loginFailed");
      setError(message);
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleFingerprintLogin() {
    setError(null);

    if (!webauthnState.isSupported) {
      setError(t("login.fingerprintNotSupported"));
      return;
    }

    if (!empId.trim()) {
      setError(t("validation.empIdRequired"));
      return;
    }

    setIsFingerprintLoading(true);
    try {
      const accessToken = await authenticate(empId);
      if (accessToken) {
        saveLastEmpId(empId);
        loginWithToken(accessToken);
        router.push("/dashboard");
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : t("login.loginFailed");
      setError(message);
    } finally {
      setIsFingerprintLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gradient-to-br from-[#4ec6c1] via-[#6dcf7c] to-[#b8d84e] px-4 py-8">
      <LanguageSwitcher />
      <div className="w-full max-w-sm space-y-6 rounded-2xl bg-white/90 p-8 shadow-xl backdrop-blur-sm">
        <div className="text-center">
          <h1 className="bg-gradient-to-r from-[#4ec6c1] to-[#6dcf7c] bg-clip-text text-2xl font-bold tracking-tight text-transparent">
            {t("login.title")}
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            {t("login.subtitle")}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="emp-id"
              className="block text-sm font-medium text-gray-700"
            >
              {t("login.empId")}
            </label>
            <input
              id="emp-id"
              type="text"
              autoComplete="username"
              required
              value={empId}
              onChange={(e) => setEmpId(e.target.value)}
              className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-gray-900 shadow-sm placeholder:text-gray-400 focus:border-[#4ec6c1] focus:ring-2 focus:ring-[#4ec6c1] focus:outline-none sm:text-sm"
              placeholder={t("login.empIdPlaceholder")}
            />
          </div>

          <div>
            <label
              htmlFor="password"
              className="block text-sm font-medium text-gray-700"
            >
              {t("login.password")}
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-gray-900 shadow-sm placeholder:text-gray-400 focus:border-[#4ec6c1] focus:ring-2 focus:ring-[#4ec6c1] focus:outline-none sm:text-sm"
              placeholder={t("login.passwordPlaceholder")}
            />
          </div>

          {error && (
            <div
              role="alert"
              className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
            >
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full rounded-lg bg-gradient-to-r from-[#4ec6c1] to-[#6dcf7c] px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:from-[#45b5b0] hover:to-[#5fc06e] focus:ring-2 focus:ring-[#4ec6c1] focus:ring-offset-2 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSubmitting ? t("login.signingIn") : t("login.signIn")}
          </button>
        </form>

        {/* Fingerprint Login */}
        {webauthnState.isSupported && (
          <>
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-gray-300" />
              </div>
              <div className="relative flex justify-center text-sm">
                <span className="bg-white/90 px-2 text-gray-500">{t("login.or")}</span>
              </div>
            </div>

            <button
              type="button"
              onClick={handleFingerprintLogin}
              disabled={isFingerprintLoading}
              className="flex w-full items-center justify-center gap-2 rounded-lg border-2 border-[#4ec6c1] px-4 py-2.5 text-sm font-semibold text-[#4ec6c1] transition-colors hover:bg-[#e8faf9] focus:ring-2 focus:ring-[#4ec6c1] focus:ring-offset-2 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Fingerprint className="h-5 w-5" />
              {isFingerprintLoading
                ? t("login.fingerprintAuthenticating")
                : t("login.fingerprintLogin")}
            </button>
          </>
        )}
      </div>

      <footer className="mt-6 text-center text-xs text-white/80 drop-shadow-sm">
        {t("login.copyright")}
      </footer>
    </div>
  );
}
