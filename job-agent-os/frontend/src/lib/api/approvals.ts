/** Approvals API */

import { api } from "./client";
import type { ApprovalRespondRequest, ApprovalResponse } from "@/types/approval";

export function listApprovals(params?: { status?: string; session_id?: string }) {
  const query = new URLSearchParams();
  if (params?.status) query.set("status", params.status);
  if (params?.session_id) query.set("session_id", params.session_id);
  const qs = query.toString();
  return api.get<ApprovalResponse[]>(`/v1/approvals${qs ? `?${qs}` : ""}`);
}

export function getApproval(approvalId: string) {
  return api.get<ApprovalResponse>(`/v1/approvals/${approvalId}`);
}

export function respondToApproval(
  approvalId: string,
  data: ApprovalRespondRequest
) {
  return api.post<ApprovalResponse>(`/v1/approvals/${approvalId}/respond`, data);
}
