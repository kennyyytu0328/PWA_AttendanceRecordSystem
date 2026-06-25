import { afterEach, describe, expect, it } from "vitest";

import { getLastEmpId, saveLastEmpId } from "@/lib/lastEmpId";

describe("lastEmpId storage", () => {
  afterEach(() => {
    localStorage.clear();
  });

  it("returns an empty string when nothing is stored", () => {
    expect(getLastEmpId()).toBe("");
  });

  it("persists and reads back the last employee ID", () => {
    saveLastEmpId("EMP123");
    expect(getLastEmpId()).toBe("EMP123");
  });

  it("trims surrounding whitespace before storing", () => {
    saveLastEmpId("  EMP999  ");
    expect(getLastEmpId()).toBe("EMP999");
  });

  it("ignores blank values and keeps any previous value", () => {
    saveLastEmpId("EMP123");
    saveLastEmpId("   ");
    expect(getLastEmpId()).toBe("EMP123");
  });
});
