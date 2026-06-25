/**
 * Remembers the employee ID used for the most recent successful login so the
 * login form can prefill it next time. Stores only the (non-secret) employee
 * ID — never the password. Degrades gracefully when storage is unavailable
 * (SSR, private mode, disabled storage).
 */

const STORAGE_KEY = "last_emp_id";

/** Read the most recently used employee ID (empty string if none/unavailable). */
export function getLastEmpId(): string {
  if (typeof window === "undefined") {
    return "";
  }
  try {
    return localStorage.getItem(STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

/** Persist the employee ID from a successful login. Blank values are ignored. */
export function saveLastEmpId(empId: string): void {
  if (typeof window === "undefined") {
    return;
  }
  const trimmed = empId.trim();
  if (!trimmed) {
    return;
  }
  try {
    localStorage.setItem(STORAGE_KEY, trimmed);
  } catch {
    // Non-fatal — remembering the username is a convenience, not a requirement.
  }
}
