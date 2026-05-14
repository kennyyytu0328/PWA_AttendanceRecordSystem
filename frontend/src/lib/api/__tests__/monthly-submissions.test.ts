import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import { monthlySubmissionsApi } from "@/lib/api/monthly-submissions";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("monthlySubmissionsApi", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe("submit", () => {
    it("POSTs body to /api/monthly-submissions and returns the submission", async () => {
      const submission = {
        emp_id: "EMP001",
        year: 2026,
        month: 5,
        submitted_at: "2026-05-14T10:00:00Z",
      };
      fetchMock.mockResolvedValueOnce(jsonResponse(submission));

      const result = await monthlySubmissionsApi.submit("EMP001", 2026, 5);

      expect(result).toEqual(submission);
      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url, options] = fetchMock.mock.calls[0];
      expect(url).toContain("/api/monthly-submissions");
      expect(options.method).toBe("POST");
      expect(JSON.parse(options.body as string)).toEqual({
        emp_id: "EMP001",
        year: 2026,
        month: 5,
      });
    });
  });

  describe("getStatus", () => {
    it("GETs /api/monthly-submissions with query string", async () => {
      const status = { submitted: true, submitted_at: "2026-05-14T10:00:00Z" };
      fetchMock.mockResolvedValueOnce(jsonResponse(status));

      const result = await monthlySubmissionsApi.getStatus("EMP001", 2026, 5);

      expect(result).toEqual(status);
      const [url, options] = fetchMock.mock.calls[0];
      expect(options.method).toBe("GET");
      expect(url).toContain("/api/monthly-submissions");
      expect(url).toContain("emp_id=EMP001");
      expect(url).toContain("year=2026");
      expect(url).toContain("month=5");
    });
  });

  it("throws ApiError on non-2xx", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "forbidden" }), {
        status: 403,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(
      monthlySubmissionsApi.submit("EMP001", 2026, 5),
    ).rejects.toBeInstanceOf(ApiError);
  });
});
