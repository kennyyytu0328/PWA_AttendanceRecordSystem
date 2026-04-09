import { renderHook, act } from "@testing-library/react";
import { useWebAuthn } from "@/hooks/useWebAuthn";
import type {
  RegistrationResponseJSON,
  AuthenticationResponseJSON,
} from "@simplewebauthn/browser";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------
const mockStartRegistration = vi.fn();
const mockStartAuthentication = vi.fn();

vi.mock("@simplewebauthn/browser", () => ({
  startRegistration: (...args: unknown[]) => mockStartRegistration(...args),
  startAuthentication: (...args: unknown[]) => mockStartAuthentication(...args),
}));

const mockPost = vi.fn();

vi.mock("@/lib/api", () => ({
  apiClient: {
    post: (...args: unknown[]) => mockPost(...args),
  },
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
const fakeRegOptions = {
  rp: { name: "GoGoFresh", id: "localhost" },
  user: { id: "abc", name: "test", displayName: "Test" },
  challenge: "random-challenge",
  pubKeyCredParams: [{ type: "public-key" as const, alg: -7 }],
  timeout: 60000,
  attestation: "none" as const,
};

const fakeRegResponse: RegistrationResponseJSON = {
  id: "cred-id",
  rawId: "cred-raw-id",
  response: {
    clientDataJSON: "cdj",
    attestationObject: "ao",
  },
  type: "public-key",
  clientExtensionResults: {},
  authenticatorAttachment: "platform",
};

const fakeAuthOptions = {
  challenge: "auth-challenge",
  timeout: 60000,
  rpId: "localhost",
  allowCredentials: [],
};

const fakeAuthResponse: AuthenticationResponseJSON = {
  id: "cred-id",
  rawId: "cred-raw-id",
  response: {
    clientDataJSON: "cdj",
    authenticatorData: "ad",
    signature: "sig",
  },
  type: "public-key",
  clientExtensionResults: {},
  authenticatorAttachment: "platform",
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe("useWebAuthn", () => {
  beforeEach(() => {
    vi.stubGlobal("PublicKeyCredential", class {});
    mockPost.mockReset();
    mockStartRegistration.mockReset();
    mockStartAuthentication.mockReset();
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  // ---- Test 1 ----
  it("isSupported is true when PublicKeyCredential exists", () => {
    const { result } = renderHook(() => useWebAuthn());

    expect(result.current.state.isSupported).toBe(true);
    expect(result.current.state.loading).toBe(false);
    expect(result.current.state.error).toBeNull();
  });

  // ---- Test 2 ----
  it("isSupported is false when PublicKeyCredential does not exist", () => {
    vi.stubGlobal("PublicKeyCredential", undefined);

    const { result } = renderHook(() => useWebAuthn());

    expect(result.current.state.isSupported).toBe(false);
  });

  // ---- Test 3 ----
  it("register calls API and simplewebauthn in correct order", async () => {
    mockPost
      .mockResolvedValueOnce(fakeRegOptions) // generate-options
      .mockResolvedValueOnce({ verified: true }); // verify
    mockStartRegistration.mockResolvedValueOnce(fakeRegResponse);

    const { result } = renderHook(() => useWebAuthn());

    let success: boolean = false;
    await act(async () => {
      success = await result.current.register();
    });

    expect(success).toBe(true);
    expect(result.current.state.error).toBeNull();
    expect(result.current.state.loading).toBe(false);

    // Verify call order
    expect(mockPost).toHaveBeenCalledTimes(2);
    expect(mockPost).toHaveBeenNthCalledWith(
      1,
      "/api/auth/register/generate-options",
    );
    expect(mockStartRegistration).toHaveBeenCalledWith({
      optionsJSON: fakeRegOptions,
    });
    expect(mockPost).toHaveBeenNthCalledWith(
      2,
      "/api/auth/register/verify",
      fakeRegResponse,
    );
  });

  // ---- Test 4 ----
  it("register handles errors gracefully", async () => {
    mockPost.mockRejectedValueOnce(new Error("Network failure"));

    const { result } = renderHook(() => useWebAuthn());

    let success: boolean = true;
    await act(async () => {
      success = await result.current.register();
    });

    expect(success).toBe(false);
    expect(result.current.state.error).toBe("Network failure");
    expect(result.current.state.loading).toBe(false);
  });

  // ---- Test 5 ----
  it("authenticate stores token on success", async () => {
    const tokenResponse = {
      access_token: "jwt-token-abc",
      token_type: "bearer",
    };
    mockPost
      .mockResolvedValueOnce(fakeAuthOptions) // generate-options
      .mockResolvedValueOnce(tokenResponse); // verify
    mockStartAuthentication.mockResolvedValueOnce(fakeAuthResponse);

    const { result } = renderHook(() => useWebAuthn());

    let success: boolean = false;
    await act(async () => {
      success = await result.current.authenticate("EMP001");
    });

    expect(success).toBe(true);
    expect(result.current.state.error).toBeNull();
    expect(result.current.state.loading).toBe(false);

    // Verify API calls
    expect(mockPost).toHaveBeenNthCalledWith(
      1,
      "/api/auth/authenticate/generate-options",
      { emp_id: "EMP001" },
    );
    expect(mockStartAuthentication).toHaveBeenCalledWith({
      optionsJSON: fakeAuthOptions,
    });
    expect(mockPost).toHaveBeenNthCalledWith(
      2,
      "/api/auth/authenticate/verify",
      { credential: fakeAuthResponse, emp_id: "EMP001" },
    );

    // Verify token stored
    expect(localStorage.getItem("access_token")).toBe("jwt-token-abc");
  });

  // ---- Test 6 ----
  it("authenticate handles errors gracefully", async () => {
    mockPost.mockResolvedValueOnce(fakeAuthOptions);
    mockStartAuthentication.mockRejectedValueOnce(
      new Error("Authenticator not found"),
    );

    const { result } = renderHook(() => useWebAuthn());

    let success: boolean = true;
    await act(async () => {
      success = await result.current.authenticate("EMP001");
    });

    expect(success).toBe(false);
    expect(result.current.state.error).toBe("Authenticator not found");
    expect(result.current.state.loading).toBe(false);

    // Verify token was NOT stored
    expect(localStorage.getItem("access_token")).toBeNull();
  });
});
