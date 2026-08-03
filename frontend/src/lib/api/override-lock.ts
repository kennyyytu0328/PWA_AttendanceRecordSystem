import { apiClient } from "@/lib/api";

export interface OverrideLockState {
  readonly locked: boolean;
}

export const overrideLockApi = {
  get: () => apiClient.get<OverrideLockState>("/api/admin/override-lock"),
  set: (locked: boolean) =>
    apiClient.put<OverrideLockState>("/api/admin/override-lock", { locked }),
};
