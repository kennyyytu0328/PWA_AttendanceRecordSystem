"use client";

import { useCallback, useEffect, useState } from "react";
import {
  startRegistration,
  startAuthentication,
} from "@simplewebauthn/browser";
import type {
  PublicKeyCredentialCreationOptionsJSON,
  PublicKeyCredentialRequestOptionsJSON,
} from "@simplewebauthn/browser";
import { apiClient } from "@/lib/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
export interface WebAuthnState {
  readonly isSupported: boolean;
  readonly loading: boolean;
  readonly error: string | null;
}

interface AuthVerifyResponse {
  readonly access_token: string;
  readonly token_type: string;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------
export function useWebAuthn(): {
  state: WebAuthnState;
  register: () => Promise<boolean>;
  authenticate: (empId: string) => Promise<string | null>;
} {
  const [isSupported, setIsSupported] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setIsSupported(!!window.PublicKeyCredential);
  }, []);
  const [error, setError] = useState<string | null>(null);

  const register = useCallback(async (): Promise<boolean> => {
    setLoading(true);
    setError(null);

    try {
      const options =
        await apiClient.post<PublicKeyCredentialCreationOptionsJSON>(
          "/api/auth/register/generate-options",
        );

      const credential = await startRegistration({ optionsJSON: options });

      await apiClient.post("/api/auth/register/verify", credential);

      return true;
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Registration failed";
      setError(message);
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  const authenticate = useCallback(
    async (empId: string): Promise<string | null> => {
      setLoading(true);
      setError(null);

      try {
        const options =
          await apiClient.post<PublicKeyCredentialRequestOptionsJSON>(
            "/api/auth/authenticate/generate-options",
            { emp_id: empId },
          );

        const credential = await startAuthentication({ optionsJSON: options });

        const response = await apiClient.post<AuthVerifyResponse>(
          "/api/auth/authenticate/verify",
          { ...credential, emp_id: empId },
        );

        return response.access_token;
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Authentication failed";
        setError(message);
        return null;
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  const state: WebAuthnState = {
    isSupported,
    loading,
    error,
  };

  return { state, register, authenticate };
}
