/** Shared TypeScript types matching the backend schemas. */

export type Role = "EMPLOYEE" | "MANAGER" | "HR" | "ADMIN";

export type WorkMode = "OFFICE" | "WFH";

export type AttendanceStatus =
  | "NORMAL"
  | "LATE"
  | "EARLY_LEAVE"
  | "LATE_AND_EARLY_LEAVE"
  | "ABNORMAL"
  | "ABSENT";

// ---------------------------------------------------------------------------
// Employee
// ---------------------------------------------------------------------------
export interface Employee {
  readonly emp_id: string;
  readonly name: string;
  readonly department: string;
  readonly role: Role;
  readonly shift_start_time: string;
  readonly shift_end_time: string;
}

export interface EmployeeCreate {
  readonly emp_id: string;
  readonly name: string;
  readonly department: string;
  readonly role: Role;
  readonly password: string;
  readonly shift_start_time: string;
  readonly shift_end_time: string;
}

export interface EmployeeUpdate {
  readonly name?: string;
  readonly department?: string;
  readonly role?: Role;
  readonly password?: string;
  readonly shift_start_time?: string;
  readonly shift_end_time?: string;
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------
export interface LoginRequest {
  readonly emp_id: string;
  readonly password: string;
}

export interface TokenResponse {
  readonly access_token: string;
  readonly token_type: string;
}

export interface AuthUser {
  readonly emp_id: string;
  readonly role: Role;
}

// ---------------------------------------------------------------------------
// Attendance
// ---------------------------------------------------------------------------
export interface PunchRequest {
  readonly latitude: number;
  readonly longitude: number;
  readonly accuracy: number;
}

export interface AttendanceLog {
  readonly id: number;
  readonly emp_id: string;
  readonly timestamp: string;
  readonly work_mode: WorkMode;
  readonly latitude: number;
  readonly longitude: number;
  readonly accuracy: number;
  readonly ip_address: string | null;
  readonly is_overridden: boolean;
  readonly override_reason: string | null;
}

export interface PunchResponse {
  readonly work_mode: WorkMode;
  readonly distance_km: number;
  readonly is_low_accuracy: boolean;
  readonly tardiness_status: AttendanceStatus | null;
  readonly summary_id: number | null;
}

// ---------------------------------------------------------------------------
// Reports
// ---------------------------------------------------------------------------
export interface DailyAttendanceSummary {
  readonly id: number;
  readonly emp_id: string;
  readonly date: string;
  readonly first_clock_in: string | null;
  readonly last_clock_out: string | null;
  readonly status: AttendanceStatus;
}

// ---------------------------------------------------------------------------
// System Config
// ---------------------------------------------------------------------------
export interface OfficeLocation {
  readonly latitude: number;
  readonly longitude: number;
}

export interface SystemConfig {
  readonly key: string;
  readonly value: unknown;
  readonly description: string | null;
}

// ---------------------------------------------------------------------------
// Workday Calendar
// ---------------------------------------------------------------------------
export interface WorkdayInfo {
  readonly date: string;
  readonly weekday_zh: string;
  readonly is_holiday: boolean;
  readonly description: string;
  readonly is_makeup_workday: boolean;
}

export interface WorkdaysResponse {
  readonly year: number;
  readonly month: number;
  readonly days: readonly WorkdayInfo[];
}

export interface CalendarStatus {
  readonly year: number;
  readonly loaded: boolean;
  readonly entry_count?: number;
  readonly updated_at?: string;
  readonly updated_by?: string;
}

export interface CalendarStatusResponse {
  readonly calendars: readonly CalendarStatus[];
}

// ---------------------------------------------------------------------------
// Bulk Override
// ---------------------------------------------------------------------------
export interface BulkOverrideEntry {
  readonly date: string;
  readonly first_clock_in: string | null;
  readonly last_clock_out: string | null;
}

export interface BulkOverrideRequest {
  readonly year: number;
  readonly month: number;
  readonly emp_id?: string;
  readonly entries: readonly BulkOverrideEntry[];
}

export interface BulkOverrideDayResult {
  readonly date: string;
  readonly first_clock_in: string | null;
  readonly last_clock_out: string | null;
  readonly status: string | null;
}

export interface BulkOverrideResponse {
  readonly emp_id: string;
  readonly updated_count: number;
  readonly results: readonly BulkOverrideDayResult[];
}

// ---------------------------------------------------------------------------
// API Response wrapper
// ---------------------------------------------------------------------------
export interface ApiError {
  readonly detail: string;
}
