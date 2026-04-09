"use client";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { useTranslation } from "@/lib/i18n";

interface BackButtonProps {
  readonly className?: string;
}

export function BackButton({ className = "" }: BackButtonProps) {
  const { t } = useTranslation();

  return (
    <Link
      href="/dashboard"
      className={`inline-flex items-center gap-1.5 text-sm font-medium text-gray-500 transition-colors hover:text-[#4ec6c1] ${className}`}
    >
      <ArrowLeft className="h-4 w-4" />
      <span>{t("common.backToDashboard")}</span>
    </Link>
  );
}
