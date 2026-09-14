/** API client with unified response handling, auth injection and token refresh. */

import { ApiError, type ApiResponse } from "@/types/api";

const API_BASE = ""; // Uses Next.js rewrites proxy to backend
const REQUEST_TIMEOUT_MS = 30000;

let accessToken: string | null = null;
let isRefreshing = false;
let refreshSubscribers: Array<(token: string | null) => void> = [];

export function setTokens(access: string | null, refresh: string | null) {
  accessToken = access;
  if (typeof window !== "undefined") {
    // Access tokens are short-lived and scoped to this tab. Refresh tokens are
    // set by the backend as HttpOnly cookies and are never exposed to JS.
    if (access) sessionStorage.setItem("access_token", access);
    else sessionStorage.removeItem("access_token");
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
  }
}

export function loadTokens() {
  if (typeof window === "undefined") return;
  accessToken = sessionStorage.getItem("access_token");
}

export function getAccessToken() {
  return accessToken;
}

function onTokenRefreshed(token: string | null) {
  refreshSubscribers.forEach((cb) => cb(token));
  refreshSubscribers = [];
}

function addRefreshSubscriber(cb: (token: string | null) => void) {
  refreshSubscribers.push(cb);
}

async function tryRefreshToken(): Promise<string | null> {
  try {
    const res = await fetch(`${API_BASE}/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
      credentials: "same-origin",
    });
    const json: ApiResponse<{ access_token: string; refresh_token: string }> =
      await res.json();
    if (json.code === 0 && json.data?.access_token) {
      setTokens(json.data.access_token, null);
      return json.data.access_token;
    }
    return null;
  } catch {
    return null;
  }
}

/** Attempt to refresh the access token. Returns the new token or null. */
export const refreshTokenFn = tryRefreshToken;

export interface RequestOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  /** Skip auth header (e.g. login/register) */
  noAuth?: boolean;
}

export async function request<T>(
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  const { method = "GET", body, headers = {}, noAuth = false } = options;

  // NOTE: Token hydration race condition is mitigated by the MainLayout guard,
  // which waits for `isHydrated` (set after loadTokens()) before rendering
  // child components. Therefore, no API call from a child component can reach
  // this function before tokens are loaded from localStorage.

  const finalHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    ...headers,
  };

  if (!noAuth && accessToken) {
    finalHeaders["Authorization"] = `Bearer ${accessToken}`;
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    let res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: finalHeaders,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
      credentials: "same-origin",
    });

    // Handle 401 -> attempt token refresh once
    if (res.status === 401 && !noAuth && !isRefreshing) {
      isRefreshing = true;
      const newToken = await tryRefreshToken();
      isRefreshing = false;
      onTokenRefreshed(newToken);

      if (newToken) {
        // Retry original request with new token
        finalHeaders["Authorization"] = `Bearer ${newToken}`;
        res = await fetch(`${API_BASE}${path}`, {
          method,
          headers: finalHeaders,
          body: body !== undefined ? JSON.stringify(body) : undefined,
          signal: controller.signal,
          credentials: "same-origin",
        });
      } else {
        // Refresh failed -> force logout
        setTokens(null, null);
        if (typeof window !== "undefined") {
          window.location.href = "/login";
        }
        throw new ApiError(40100, "登录已过期，请重新登录", 401);
      }
    } else if (res.status === 401 && !noAuth && isRefreshing) {
      // Wait for ongoing refresh
      const newToken = await new Promise<string | null>((resolve) =>
        addRefreshSubscriber(resolve)
      );
      if (!newToken) {
        setTokens(null, null);
        throw new ApiError(40100, "登录已过期，请重新登录", 401);
      }
      finalHeaders["Authorization"] = `Bearer ${newToken}`;
      res = await fetch(`${API_BASE}${path}`, {
        method,
        headers: finalHeaders,
        body: body !== undefined ? JSON.stringify(body) : undefined,
        signal: controller.signal,
        credentials: "same-origin",
      });
    }

    let json: ApiResponse<T>;
    try {
      // 204 No Content has no body (e.g. DELETE endpoints)
      if (res.status === 204) {
        return null as T;
      }
      json = await res.json();
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") {
        throw new ApiError(408, "请求超时，请稍后重试", 408);
      }
      throw new ApiError(res.status, `请求失败 (${res.status})`, res.status);
    }

    if (json.code !== 0) {
      throw new ApiError(json.code, json.message, res.status);
    }

    return json.data;
  } catch (e) {
    if (e instanceof ApiError) throw e;
    if (e instanceof DOMException && e.name === "AbortError") {
      throw new ApiError(408, "请求超时，请稍后重试", 408);
    }
    throw new ApiError(
      0,
      `网络请求失败: ${e instanceof Error ? e.message : "未知错误"}`,
      0
    );
  } finally {
    clearTimeout(timeoutId);
  }
}

export const api = {
  get: <T>(path: string, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "POST", body }),
  patch: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "PATCH", body }),
  put: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "PUT", body }),
  delete: <T>(path: string, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "DELETE" }),
};
