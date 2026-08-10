/** Sessions API */

import { api } from "./client";
import type { RecommendationFeedbackRequest, RecommendationItem } from "@/types/job";
import type {
  SessionCreateRequest,
  SessionLogEntry,
  SessionMessageRequest,
  SessionMessageResponse,
  SessionResponse,
  TimelineEvent,
} from "@/types/session";

export function createSession(data: SessionCreateRequest) {
  return api.post<SessionResponse>("/v1/sessions", data);
}

export function getSession(sessionId: string) {
  return api.get<SessionResponse>(`/v1/sessions/${sessionId}`);
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
