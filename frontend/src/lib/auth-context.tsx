"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { useRouter } from "next/navigation";

import { apiClient } from "@/lib/api";
import type { AuthUser, Role, TokenResponse } from "@/types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AuthContextType {
  readonly user: AuthUser | null;
  readonly token: string | null;
  readonly login: (empId: string, password: string) => Promise<void>;
  readonly loginWithToken: (accessToken: string) => void;
  readonly logout: () => void;
  readonly isAuthenticated: boolean;
  readonly isLoading: boolean;
}

// ---------------------------------------------------------------------------
// JWT Helpers
// ---------------------------------------------------------------------------

interface JwtPayload {
  readonly sub: string;
  readonly role: Role;
}

function decodeToken(token: string): AuthUser | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) {
      return null;
    }
    const payload: JwtPayload = JSON.parse(atob(parts[1]));
    if (!payload.sub || !payload.role) {
      return null;
    }
    return { emp_id: payload.sub, role: payload.role };
  } catch {
    return null;
  }
}

function getStoredToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return localStorage.getItem("access_token");
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const AuthContext = createContext<AuthContextType | null>(null);

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

interface AuthProviderProps {
  readonly children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Restore token from localStorage on client mount
  useEffect(() => {
    const stored = getStoredToken();
    if (stored) {
      setToken(stored);
      setUser(decodeToken(stored));
    }
    setIsLoading(false);
  }, []);

  const login = useCallback(
    async (empId: string, password: string): Promise<void> => {
      const response = await apiClient.post<TokenResponse>(
        "/api/auth/login",
        { emp_id: empId, password },
      );
      const newToken = response.access_token;
      localStorage.setItem("access_token", newToken);
      setToken(newToken);
      setUser(decodeToken(newToken));
    },
    [],
  );

  const loginWithToken = useCallback((accessToken: string) => {
    localStorage.setItem("access_token", accessToken);
    setToken(accessToken);
    setUser(decodeToken(accessToken));
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("access_token");
    setToken(null);
    setUser(null);
    router.push("/login");
  }, [router]);

  const isAuthenticated = user !== null;

  const value = useMemo<AuthContextType>(
    () => ({ user, token, login, loginWithToken, logout, isAuthenticated, isLoading }),
    [user, token, login, loginWithToken, logout, isAuthenticated, isLoading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
