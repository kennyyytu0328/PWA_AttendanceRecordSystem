import { apiClient } from "@/lib/api";

export interface MonthlySubmission {
  emp_id: string;
  year: number;
  month: number;
  submitted_at: string;
}

export interface SubmissionStatus {
  submitted: boolean;
  submitted_at: string | null;
}

export const monthlySubmissionsApi = {
  submit(
    empId: string,
    year: number,
    month: number,
  ): Promise<MonthlySubmission> {
    return apiClient.post<MonthlySubmission>("/api/monthly-submissions", {
      emp_id: empId,
      year,
      month,
    });
  },

  getStatus(
    empId: string,
    year: number,
    month: number,
  ): Promise<SubmissionStatus> {
    const query = new URLSearchParams({
      emp_id: empId,
      year: String(year),
      month: String(month),
    });
    return apiClient.get<SubmissionStatus>(
      `/api/monthly-submissions?${query.toString()}`,
    );
  },
};
