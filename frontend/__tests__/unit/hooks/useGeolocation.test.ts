import { renderHook, act } from "@testing-library/react";
import { useGeolocation } from "@/hooks/useGeolocation";

describe("useGeolocation", () => {
  const mockGetCurrentPosition = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("navigator", {
      geolocation: {
        getCurrentPosition: mockGetCurrentPosition,
      },
    });
    mockGetCurrentPosition.mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("initial state has null position and loading=false", () => {
    const { result } = renderHook(() => useGeolocation());

    expect(result.current.position.latitude).toBeNull();
    expect(result.current.position.longitude).toBeNull();
    expect(result.current.position.accuracy).toBeNull();
    expect(result.current.position.error).toBeNull();
    expect(result.current.position.loading).toBe(false);
  });

  it("requestPosition sets loading to true", () => {
    // Never call the callbacks so loading stays true
    mockGetCurrentPosition.mockImplementation(() => {});

    const { result } = renderHook(() => useGeolocation());

    act(() => {
      result.current.requestPosition();
    });

    expect(result.current.position.loading).toBe(true);
  });

  it("successful position updates lat/lng/accuracy", () => {
    mockGetCurrentPosition.mockImplementation(
      (onSuccess: PositionCallback) => {
        onSuccess({
          coords: {
            latitude: 25.033,
            longitude: 121.5654,
            accuracy: 10,
            altitude: null,
            altitudeAccuracy: null,
            heading: null,
            speed: null,
          },
          timestamp: Date.now(),
        } as GeolocationPosition);
      },
    );

    const { result } = renderHook(() => useGeolocation());

    act(() => {
      result.current.requestPosition();
    });

    expect(result.current.position.latitude).toBe(25.033);
    expect(result.current.position.longitude).toBe(121.5654);
    expect(result.current.position.accuracy).toBe(10);
    expect(result.current.position.error).toBeNull();
    expect(result.current.position.loading).toBe(false);
  });

  it("geolocation error sets error message", () => {
    mockGetCurrentPosition.mockImplementation(
      (_onSuccess: PositionCallback, onError?: PositionErrorCallback) => {
        onError?.({
          code: 2,
          message: "Position unavailable",
          PERMISSION_DENIED: 1,
          POSITION_UNAVAILABLE: 2,
          TIMEOUT: 3,
        } as GeolocationPositionError);
      },
    );

    const { result } = renderHook(() => useGeolocation());

    act(() => {
      result.current.requestPosition();
    });

    expect(result.current.position.error).toBe("Position unavailable");
    expect(result.current.position.latitude).toBeNull();
    expect(result.current.position.longitude).toBeNull();
    expect(result.current.position.accuracy).toBeNull();
    expect(result.current.position.loading).toBe(false);
  });

  it("permission denied sets specific error", () => {
    mockGetCurrentPosition.mockImplementation(
      (_onSuccess: PositionCallback, onError?: PositionErrorCallback) => {
        onError?.({
          code: 1,
          message: "User denied Geolocation",
          PERMISSION_DENIED: 1,
          POSITION_UNAVAILABLE: 2,
          TIMEOUT: 3,
        } as GeolocationPositionError);
      },
    );

    const { result } = renderHook(() => useGeolocation());

    act(() => {
      result.current.requestPosition();
    });

    expect(result.current.position.error).toBe(
      "Location permission denied. Please enable location access in your browser settings.",
    );
    expect(result.current.position.loading).toBe(false);
  });

  it("geolocation not supported sets error", () => {
    vi.stubGlobal("navigator", {});

    const { result } = renderHook(() => useGeolocation());

    act(() => {
      result.current.requestPosition();
    });

    expect(result.current.position.error).toBe(
      "Geolocation is not supported by this browser.",
    );
    expect(result.current.position.loading).toBe(false);
  });
});
