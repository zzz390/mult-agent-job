/** useAuth hook - wraps login/register/logout logic. */

"use client";

import { useCallback } from "react";
import { useRouter } from "next/navigation";
import * as authApi from "@/lib/api/auth";
import { useAuthStore } from "@/stores/auth-store";
import type { LoginRequest, RegisterRequest } from "@/types/auth";

export function useAuth() {
  const router = useRouter();
  const { setAuth, clearAuth, isAuthenticated, username, isHydrated } =
    useAuthStore();

  const login = useCallback(
    async (data: LoginRequest) => {
      const tokens = await authApi.login(data);
      setAuth(tokens.user_id, tokens.username, tokens.access_token, tokens.refresh_token);
      router.push("/chat");
    },
    [setAuth, router]
  );

  const register = useCallback(
    async (data: RegisterRequest) => {
      const tokens = await authApi.register(data);
      setAuth(tokens.user_id, tokens.username, tokens.access_token, tokens.refresh_token);
      router.push("/chat");
    },
    [setAuth, router]
  );

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      // Ignore logout API errors
    }
    clearAuth();
    router.push("/login");
  }, [clearAuth, router]);

  return { login, register, logout, isAuthenticated, username, isHydrated };
}
