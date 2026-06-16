import { apiClient } from "@/lib/api";

export interface RanksResponse {
  ranks: string[];
}

export interface OrgScopingResponse {
  enabled: boolean;
}

export const ranksApi = {
  list(): Promise<RanksResponse> {
    return apiClient.get<RanksResponse>("/api/admin/ranks");
  },

  update(ranks: string[]): Promise<RanksResponse> {
    return apiClient.put<RanksResponse>("/api/admin/ranks", { ranks });
  },
};

export const orgScopingApi = {
  get(): Promise<OrgScopingResponse> {
    return apiClient.get<OrgScopingResponse>("/api/admin/org-scoping");
  },

  set(enabled: boolean): Promise<OrgScopingResponse> {
    return apiClient.put<OrgScopingResponse>("/api/admin/org-scoping", {
      enabled,
    });
  },
};
