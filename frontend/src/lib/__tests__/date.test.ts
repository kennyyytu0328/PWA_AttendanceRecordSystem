// Pin to Taipei (UTC+8) so the pre-08:00 date-rollback bug these helpers guard
// against is exercised deterministically regardless of the CI host timezone.
process.env.TZ = "Asia/Taipei";

import { describe, expect, it } from "vitest";

import { isoDateOnly, localDateString, localToday } from "@/lib/date";

describe("isoDateOnly", () => {
  it("keeps the literal date for a pre-08:00 naive timestamp (no UTC rollback)", () => {
    expect(isoDateOnly("2026-07-01T07:41:00")).toBe("2026-07-01");
  });

  it("keeps the literal date for a late-evening timestamp", () => {
    expect(isoDateOnly("2026-07-01T23:59:00")).toBe("2026-07-01");
  });
});

describe("localDateString", () => {
  it("formats a Date from its local components without rolling back", () => {
    // Local 2026-07-01 07:41 — must NOT become 06-30.
    expect(localDateString(new Date(2026, 6, 1, 7, 41))).toBe("2026-07-01");
  });

  it("zero-pads month and day", () => {
    expect(localDateString(new Date(2026, 0, 5, 0, 0))).toBe("2026-01-05");
  });
});

describe("localToday", () => {
  it("returns a YYYY-MM-DD string", () => {
    expect(localToday()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});
