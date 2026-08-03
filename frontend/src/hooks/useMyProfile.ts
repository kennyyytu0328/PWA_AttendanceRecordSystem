"use client";

import { useEffect, useState } from "react";

import { apiClient } from "@/lib/api";
import type { MyProfile } from "@/types";

/** Fetches /api/auth/me once — shift times drive the late-leave dialog. */
export function useMyProfile(enabled: boolean): { profile: MyProfile | null } {
  const [profile, setProfile] = useState<MyProfile | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    apiClient
      .get<MyProfile>("/api/auth/me")
      .then((data) => {
        if (!cancelled) setProfile(data);
      })
      .catch(() => {
        // silent — without shift times the dialog simply never triggers
      });
    return () => {
      cancelled = true;
    };
  }, [enabled]);

  return { profile };
}
