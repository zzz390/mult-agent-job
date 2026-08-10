/** Users API */

import { api } from "./client";

export interface UserProfile {
  id: string;
  username: string;
  email: string;
  phone: string | null;
  preferences: Record<string, unknown>;
  job_intentions: unknown[];
  token_budget_daily: number;
  token_used_today: number;
  created_at: string;
}

export interface UserUpdateRequest {
  username?: string | null;
  phone?: string | null;
  preferences?: Record<string, unknown> | null;
  job_intentions?: unknown[] | null;
}

export function getCurrentUser() {
  return api.get<UserProfile>("/v1/users/me");
}

export function updateCurrentUser(data: UserUpdateRequest) {
  return api.patch<UserProfile>("/v1/users/me", data);
}
