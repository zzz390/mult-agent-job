/** Session types (matches backend schemas/session.py) */

export type SessionMode =
  | "full"
  | "search_only"
  | "match_only"
  | "resume_only"
  | "interview_only";

export interface SessionCreateRequest {
  intent: string;
  mode?: SessionMode;
  resume_id?: string | null;
  options?: Record<string, unknown>;
}

export interface SessionProgress {
  completed_steps: string[];
  current_step: string | null;
  pending_steps: string[];
}

export interface PendingApprovalInfo {
  id: string;
  type: string;
  title: string;
}

export type SessionStatus =
  | "created"
  | "running"
  | "waiting_approval"
  | "completed"
  | "failed"
  | "cancelled";

export interface SessionResponse {
  session_id: string;
  status: SessionStatus;
  intent: string | null;
  current_phase: string | null;
  progress: SessionProgress | null;
  pending_approval: PendingApprovalInfo | null;
  results_summary: Record<string, unknown>;
  token_usage: Record<string, number>;
  started_at: string | null;
  updated_at: string | null;
}

export type MessageType = "text" | "clarification" | "feedback";

export interface SessionMessageRequest {
  content: string;
  message_type?: MessageType;
}

export interface SessionMessageResponse {
  message_id: string;
  response: string;
  session_status: SessionStatus;
}

/** Timeline event (from GET /v1/sessions/{id}/timeline) */
export interface TimelineEvent {
  event: string;
  timestamp: string | null;
  data: Record<string, unknown>;
}

/** Session execution log entry (from GET /v1/sessions/{id}/logs) */
export interface SessionLogEntry {
  id: string;
  agent_name: string;
  node_name: string;
  step_order: number;
  status: string;
  duration_ms: number | null;
  total_tokens: number | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
}

/** Resume diff entry (from resume optimization approval payload) */
export interface ResumeDiffEntry {
  section?: string;
  before: string;
  after: string;
  reason: string;
}

/** Interview question (matches backend schema and interview API type) */
export interface InterviewQuestion {
  id: number;
  type: string;
  category: string;
  difficulty: string;
  question: string;
  reference_answer: string;
  scoring_criteria: string[];
  follow_up: string | null;
}
