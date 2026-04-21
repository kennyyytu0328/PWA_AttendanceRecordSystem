import { describe, expect, it } from "vitest";

import { buildExportFilename } from "@/lib/exportFilename";

describe("buildExportFilename", () => {
  const base = { startDate: "2026-04-01", endDate: "2026-04-30" } as const;

  it("uses period only when no filter is applied", () => {
    expect(buildExportFilename({ ...base, format: "csv" })).toBe(
      "attendance_report_2026-04-01_2026-04-30.csv",
    );
  });

  it("includes department when only department is set", () => {
    expect(
      buildExportFilename({ ...base, format: "xlsx", department: "Engineering" }),
    ).toBe("attendance_report_Engineering_2026-04-01_2026-04-30.xlsx");
  });

  it("preserves non-ASCII department names (Chinese)", () => {
    expect(
      buildExportFilename({ ...base, format: "csv", department: "工程部" }),
    ).toBe("attendance_report_工程部_2026-04-01_2026-04-30.csv");
  });

  it("sanitises unsafe characters in department", () => {
    expect(
      buildExportFilename({ ...base, format: "csv", department: "R&D / Ops" }),
    ).toBe("attendance_report_R&D-Ops_2026-04-01_2026-04-30.csv");
  });

  it("includes emp_id and name when employee is selected", () => {
    expect(
      buildExportFilename({
        ...base,
        format: "csv",
        empId: "EMP001",
        empName: "Alice Chen",
      }),
    ).toBe("attendance_report_EMP001_Alice-Chen_2026-04-01_2026-04-30.csv");
  });

  it("emits emp_id alone when name is missing", () => {
    expect(
      buildExportFilename({ ...base, format: "json", empId: "EMP001" }),
    ).toBe("attendance_report_EMP001_2026-04-01_2026-04-30.json");
  });

  it("employee wins when both employee and department are set", () => {
    expect(
      buildExportFilename({
        ...base,
        format: "csv",
        empId: "EMP001",
        empName: "Alice",
        department: "Engineering",
      }),
    ).toBe("attendance_report_EMP001_Alice_2026-04-01_2026-04-30.csv");
  });

  it("treats whitespace-only values as absent", () => {
    expect(
      buildExportFilename({
        ...base,
        format: "csv",
        empId: "  ",
        department: "   ",
      }),
    ).toBe("attendance_report_2026-04-01_2026-04-30.csv");
  });
});
