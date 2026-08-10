/** Approval types (matches backend schemas/approval.py) */

export type ApprovalAction = "approve" | "reject" | "modify" | "skip";

export interface ApprovalResponse {
  id: string;
  approval_type: string;
  title: string;
  description: string | null;
  payload: Record<string, unknown>;
  options: string[];
  status: string;
  timeout_seconds: number | null;
  requested_at: string;
}

export interface ApprovalRespondRequest {
  action: ApprovalAction;
  feedback?: string | null;
  modified_payload?: Record<string, unknown> | null;
}
