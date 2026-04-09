"use client";

import { useState, useCallback } from "react";
import { useTranslation } from "@/lib/i18n";

export interface GeolocationState {
  readonly latitude: number | null;
  readonly longitude: number | null;
  readonly accuracy: number | null;
  readonly error: string | null;
  readonly loading: boolean;
}

const INITIAL_STATE: GeolocationState = {
  latitude: null,
  longitude: null,
  accuracy: null,
  error: null,
  loading: false,
};

const GEOLOCATION_OPTIONS: PositionOptions = {
  enableHighAccuracy: true,
  timeout: 10000,
};

export function useGeolocation(): {
  readonly position: GeolocationState;
  readonly requestPosition: () => void;
} {
  const [position, setPosition] = useState<GeolocationState>(INITIAL_STATE);
  const { t } = useTranslation();

  const requestPosition = useCallback(() => {
    if (!navigator.geolocation) {
      setPosition({
        ...INITIAL_STATE,
        error: t("geolocation.notSupported"),
      });
      return;
    }

    setPosition((prev) => ({ ...prev, loading: true, error: null }));

    navigator.geolocation.getCurrentPosition(
      (geo: GeolocationPosition) => {
        setPosition({
          latitude: geo.coords.latitude,
          longitude: geo.coords.longitude,
          accuracy: geo.coords.accuracy,
          error: null,
          loading: false,
        });
      },
      (err: GeolocationPositionError) => {
        const message =
          err.code === err.PERMISSION_DENIED
            ? t("geolocation.permissionDenied")
            : err.message;
        setPosition({
          ...INITIAL_STATE,
          error: message,
        });
      },
      GEOLOCATION_OPTIONS,
    );
  }, [t]);

  return { position, requestPosition } as const;
}
