export type ExportFormat = "csv" | "xlsx" | "json";

interface BuildExportFilenameParams {
  readonly format: ExportFormat;
  readonly startDate: string;
  readonly endDate: string;
  readonly empId?: string;
  readonly empName?: string;
  readonly department?: string;
}

const INVALID_CHARS_RE = /[\s/\\:*?"<>|]+/g;

function sanitize(part: string): string {
  return part.replace(INVALID_CHARS_RE, "-").replace(/-+/g, "-").replace(/^-+|-+$/g, "");
}

export function buildExportFilename({
  format,
  startDate,
  endDate,
  empId,
  empName,
  department,
}: BuildExportFilenameParams): string {
  const parts: string[] = ["attendance_report"];
  const trimmedEmpId = empId?.trim();
  const trimmedDepartment = department?.trim();

  if (trimmedEmpId) {
    parts.push(sanitize(trimmedEmpId));
    const trimmedName = empName?.trim();
    if (trimmedName) {
      parts.push(sanitize(trimmedName));
    }
  } else if (trimmedDepartment) {
    parts.push(sanitize(trimmedDepartment));
  }

  parts.push(startDate, endDate);
  return `${parts.join("_")}.${format}`;
}
