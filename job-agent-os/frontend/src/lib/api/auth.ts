/** Auth API */

import { api } from "./client";
import type { LoginRequest, RegisterRequest, TokenResponse } from "@/types/auth";

export function register(data: RegisterRequest) {
  return api.post<TokenResponse>("/v1/auth/register", data, { noAuth: true });
}

export function login(data: LoginRequest) {
  return api.post<TokenResponse>("/v1/auth/login", data, { noAuth: true });
}

export function refreshToken(refresh_token: string) {
  return api.post<TokenResponse>(
    "/v1/auth/refresh",
    { refresh_token },
    { noAuth: true }
  );
}

export function logout() {
  return api.post<null>("/v1/auth/logout");
}
