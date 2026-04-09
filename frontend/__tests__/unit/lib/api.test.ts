import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Tests for the API client module
// RED phase: these should fail because src/lib/api.ts doesn't exist yet.

describe("API Client", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ data: "test" }),
          text: () => Promise.resolve("csv-data"),
          headers: new Headers({ "content-type": "application/json" }),
        })
      )
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("should make GET requests to the correct URL", async () => {
    const { apiClient } = await import("@/lib/api");
    await apiClient.get("/api/auth/me");

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/auth/me"),
      expect.objectContaining({ method: "GET" })
    );
  });

  it("should include Authorization header when token exists", async () => {
    localStorage.setItem("access_token", "test-jwt-token");
    const { apiClient } = await import("@/lib/api");
    await apiClient.get("/api/auth/me");

    expect(fetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer test-jwt-token",
        }),
      })
    );
  });

  it("should make POST requests with JSON body", async () => {
    const { apiClient } = await import("@/lib/api");
    const body = { emp_id: "EMP001", password: "pass123" };
    await apiClient.post("/api/auth/login", body);

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/auth/login"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(body),
        headers: expect.objectContaining({
          "Content-Type": "application/json",
        }),
      })
    );
  });

  it("should throw ApiError on non-ok responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: false,
          status: 401,
          json: () => Promise.resolve({ detail: "Invalid credentials" }),
        })
      )
    );

    const { apiClient, ApiError } = await import("@/lib/api");

    await expect(
      apiClient.post("/api/auth/login", { emp_id: "x", password: "y" })
    ).rejects.toThrow(ApiError);
  });

  it("should support PUT and DELETE methods", async () => {
    const { apiClient } = await import("@/lib/api");

    await apiClient.put("/api/employees/EMP001", { name: "New Name" });
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/employees/EMP001"),
      expect.objectContaining({ method: "PUT" })
    );

    await apiClient.delete("/api/employees/EMP001");
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/employees/EMP001"),
      expect.objectContaining({ method: "DELETE" })
    );
  });
});

describe("Zod Validators", () => {
  it("should validate LoginRequest schema", async () => {
    const { loginRequestSchema } = await import("@/lib/validators");
    const valid = loginRequestSchema.parse({
      emp_id: "EMP001",
      password: "pass123",
    });
    expect(valid.emp_id).toBe("EMP001");
  });

  it("should reject invalid LoginRequest", async () => {
    const { loginRequestSchema } = await import("@/lib/validators");
    expect(() =>
      loginRequestSchema.parse({ emp_id: "", password: "" })
    ).toThrow();
  });

  it("should validate PunchRequest schema", async () => {
    const { punchRequestSchema } = await import("@/lib/validators");
    const valid = punchRequestSchema.parse({
      latitude: 25.033,
      longitude: 121.565,
      accuracy: 15.5,
    });
    expect(valid.latitude).toBe(25.033);
  });

  it("should reject PunchRequest with out-of-range latitude", async () => {
    const { punchRequestSchema } = await import("@/lib/validators");
    expect(() =>
      punchRequestSchema.parse({
        latitude: 100,
        longitude: 121.565,
        accuracy: 15.5,
      })
    ).toThrow();
  });
});
