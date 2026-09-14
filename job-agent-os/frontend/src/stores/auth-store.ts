/** Auth store - access credentials live only for the current browser tab. */

import { create } from "zustand";
import { loadTokens, setTokens } from "@/lib/api/client";
import type { UserProfile } from "@/lib/api/users";
import * as usersApi from "@/lib/api/users";

interface AuthState {
  userId: string | null;
  username: string | null;
  isAuthenticated: boolean;
  isHydrated: boolean;
  user: UserProfile | null;
  setAuth: (userId: string, username: string, access: string, refresh: string) => void;
  clearAuth: () => void;
  hydrate: () => void;
  setUser: (user: UserProfile | null) => void;
  fetchUser: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  userId: null,
  username: null,
  isAuthenticated: false,
  isHydrated: false,
  user: null,

  setAuth: (userId, username, access, refresh) => {
    setTokens(access, refresh);
    if (typeof window !== "undefined") {
      localStorage.setItem("user_id", userId);
      localStorage.setItem("username", username);
    }
    set({ userId, username, isAuthenticated: true });
  },

  clearAuth: () => {
    setTokens(null, null);
    if (typeof window !== "undefined") {
      localStorage.removeItem("user_id");
      localStorage.removeItem("username");
    }
    set({ userId: null, username: null, isAuthenticated: false, user: null });
  },

  hydrate: () => {
    loadTokens();
    if (typeof window !== "undefined") {
      const userId = localStorage.getItem("user_id");
      const username = localStorage.getItem("username");
      const access = sessionStorage.getItem("access_token");
      if (userId && access) {
        set({ userId, username, isAuthenticated: true, isHydrated: true });
        return;
      }
    }
    set({ isHydrated: true });
  },

  setUser: (user) => set({ user }),

  fetchUser: async () => {
    try {
      const profile = await usersApi.getCurrentUser();
      set({ user: profile });
    } catch {
      // Silently ignore — callers can use fallback values
    }
  },
}));
