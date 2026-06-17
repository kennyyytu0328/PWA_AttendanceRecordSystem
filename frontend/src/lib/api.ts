/** Typed API client with JWT auth interceptor. */

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
    /** Stable machine-readable code when the backend returns a structured
     * detail ({code, message}); undefined for plain-string errors. Lets the UI
     * localize the message instead of showing the raw English detail. */
    public readonly code?: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

function getAuthHeaders(): Record<string, string> {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  if (token) {
    return { Authorization: `Bearer ${token}` };
  }
  return {};
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers: Record<string, string> = {
    ...getAuthHeaders(),
    ...(options.headers as Record<string, string> | undefined),
  };

  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let detail = "Request failed";
    let code: string | undefined;
    try {
      const body = await response.json();
      // detail is usually a plain string, but some endpoints return a
      // structured { code, message } so the UI can localize the message.
      if (body.detail && typeof body.detail === "object") {
        detail = body.detail.message ?? detail;
        code = body.detail.code;
      } else {
        detail = body.detail ?? detail;
      }
    } catch {
      // ignore parse errors
    }
    throw new ApiError(response.status, detail, code);
  }

  const contentType = response.headers.get("content-type");
  if (contentType?.includes("application/json")) {
    return response.json() as Promise<T>;
  }

  return response.text() as unknown as T;
}

export const apiClient = {
  get<T>(path: string): Promise<T> {
    return request<T>(path, { method: "GET" });
  },

  post<T>(path: string, body?: unknown): Promise<T> {
    return request<T>(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
  },

  put<T>(path: string, body?: unknown): Promise<T> {
    return request<T>(path, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
  },

  delete<T>(path: string): Promise<T> {
    return request<T>(path, { method: "DELETE" });
  },
};
