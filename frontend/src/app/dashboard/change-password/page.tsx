"use client";

import Link from "next/link";
import { ChevronLeft, Lock } from "lucide-react";

import { ChangePasswordForm } from "@/components/ChangePasswordForm";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { useTranslation } from "@/lib/i18n";

export default function ChangePasswordPage() {
  const { t } = useTranslation();

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#e8faf9] via-[#edfbf0] to-[#f5fbe8]">
      <LanguageSwitcher />
      <div className="mx-auto max-w-md px-4 py-8">
        <Link
          href="/dashboard"
          className="mb-6 inline-flex items-center gap-1 text-sm text-gray-600 hover:text-[#4ec6c1]"
        >
          <ChevronLeft className="h-4 w-4" />
          {t("common.backToDashboard")}
        </Link>

        <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="mb-6 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-[#4ec6c1] to-[#6dcf7c] text-white">
              <Lock className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-900">
                {t("changePassword.title")}
              </h1>
              <p className="text-sm text-gray-500">
                {t("changePassword.subtitle")}
              </p>
            </div>
          </div>

          <ChangePasswordForm />
        </div>
      </div>
    </div>
  );
}
