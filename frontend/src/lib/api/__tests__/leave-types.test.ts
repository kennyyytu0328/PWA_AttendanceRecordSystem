import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import { leaveTypesApi } from "@/lib/api/leave-types";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("leaveTypesApi", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe("list", () => {
    it("GETs /api/admin/leave-types", async () => {
      const payload = { leave_types: ["特休", "事假", "病假"] };
      fetchMock.mockResolvedValueOnce(jsonResponse(payload));

      const result = await leaveTypesApi.list();

      expect(result).toEqual(payload);
      const [url, options] = fetchMock.mock.calls[0];
      expect(url).toContain("/api/admin/leave-types");
      expect(options.method).toBe("GET");
    });
  });

  describe("update", () => {
    it("PUTs the right body to /api/admin/leave-types", async () => {
      const payload = { leave_types: ["特休", "事假"] };
      fetchMock.mockResolvedValueOnce(jsonResponse(payload));

      const result = await leaveTypesApi.update(["特休", "事假"]);

      expect(result).toEqual(payload);
      const [url, options] = fetchMock.mock.calls[0];
      expect(url).toContain("/api/admin/leave-types");
      expect(options.method).toBe("PUT");
      expect(JSON.parse(options.body as string)).toEqual({
        leave_types: ["特休", "事假"],
      });
    });
  });

  it("throws ApiError on non-2xx", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "forbidden" }), {
        status: 403,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(leaveTypesApi.update(["特休"])).rejects.toBeInstanceOf(
      ApiError,
    );
  });
});
