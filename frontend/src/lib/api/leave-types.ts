import { apiClient } from "@/lib/api";

export interface LeaveTypesResponse {
  leave_types: string[];
}

export const leaveTypesApi = {
  list(): Promise<LeaveTypesResponse> {
    return apiClient.get<LeaveTypesResponse>("/api/admin/leave-types");
  },

  update(leaveTypes: string[]): Promise<LeaveTypesResponse> {
    return apiClient.put<LeaveTypesResponse>("/api/admin/leave-types", {
      leave_types: leaveTypes,
    });
  },
};
