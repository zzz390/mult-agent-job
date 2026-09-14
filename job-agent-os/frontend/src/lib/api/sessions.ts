/** Sessions API */

import { api, getAccessToken, refreshTokenFn } from "./client";
import type { RecommendationFeedbackRequest, RecommendationItem } from "@/types/job";
import type {
  SessionCreateRequest,
  SessionLogEntry,
  SessionMessageRequest,
  SessionMessageResponse,
  SessionResponse,
  SessionStreamEvent,
  TimelineEvent,
} from "@/types/session";

async function openSessionStream(sessionId: string, token: string | null, signal: AbortSignal) {
  return fetch(`/v1/sessions/${sessionId}/stream`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    credentials: "same-origin",
    signal,
  });
}

/** Consume the authenticated SSE endpoint without putting a JWT in the URL. */
export async function streamSession(
  sessionId: string,
  onEvent: (event: SessionStreamEvent) => void | Promise<void>,
  signal: AbortSignal
) {
  let response = await openSessionStream(sessionId, getAccessToken(), signal);
  if (response.status === 401) {
    const refreshed = await refreshTokenFn();
    if (refreshed) {
      response = await openSessionStream(sessionId, refreshed, signal);
    }
  }
  if (!response.ok || !response.body) {
    throw new Error(`会话流连接失败 (${response.status})`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const frames = buffer.split(/\r?\n\r?\n/);
    buffer = frames.pop() ?? "";

    for (const frame of frames) {
      const data = frame
        .split(/\r?\n/)
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart())
        .join("\n");
      if (data) {
        await onEvent(JSON.parse(data) as SessionStreamEvent);
      }
    }
    if (done) break;
  }
}

export function createSession(data: SessionCreateRequest) {
  return api.post<SessionResponse>("/v1/sessions", data);
}

export function getSession(sessionId: string) {
  return api.get<SessionResponse>(`/v1/sessions/${sessionId}`);
}

export function deleteSession(sessionId: string) {
  return api.delete<{ session_id: string; status: "deleted" }>(
    `/v1/sessions/${sessionId}`
  );
}

export function listSessions() {
  return api.get<SessionResponse[]>("/v1/sessions");
}

export function sendMessage(sessionId: string, data: SessionMessageRequest) {
  return api.post<SessionMessageResponse>(
    `/v1/sessions/${sessionId}/messages`,
    data
  );
}

export function cancelSession(sessionId: string) {
  return api.post<{ status: string }>(`/v1/sessions/${sessionId}/cancel`);
}

export function getSessionTimeline(sessionId: string) {
  return api.get<TimelineEvent[]>(`/v1/sessions/${sessionId}/timeline`);
}

export function getSessionLogs(sessionId: string) {
  return api.get<SessionLogEntry[]>(`/v1/sessions/${sessionId}/logs`);
}

export function getRecommendations(sessionId: string) {
  return api.get<RecommendationItem[]>(
    `/v1/sessions/${sessionId}/recommendations`
  );
}

export function submitRecommendationFeedback(
  sessionId: string,
  data: RecommendationFeedbackRequest
) {
  return api.post<{ status: string; session_id: string }>(
    `/v1/sessions/${sessionId}/recommendations/feedback`,
    data
  );
}
