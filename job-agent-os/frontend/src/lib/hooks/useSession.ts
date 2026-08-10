/** useSession hook - polls session status and syncs to stores + chat stream.
 *
 * Uses a module-level singleton timer so that only ONE polling loop runs
 * regardless of how many components mount the hook.
 */

"use client";

import { useCallback } from "react";
import * as sessionsApi from "@/lib/api/sessions";
import * as approvalsApi from "@/lib/api/approvals";
import { useChatStore } from "@/stores/chat-store";
import { useSessionStore } from "@/stores/session-store";
import type { ApprovalResponse } from "@/types/approval";
import type { RecommendationItem } from "@/types/job";
import type { ResumeDiffEntry, SessionStatus } from "@/types/session";

const POLL_INTERVAL = 2000;
const TERMINAL_STATUSES: SessionStatus[] = ["completed", "failed", "cancelled"];

// Module-level singleton state
let timer: ReturnType<typeof setInterval> | null = null;
let approvalShown: string | null = null;
let resultEmitted = false;
let isPollingActive = false;

/** Normalize resume diff entries from an approval payload (defensive). */
function extractDiffs(payload: Record<string, unknown>): ResumeDiffEntry[] {
  const raw =
    (payload.resume_diff as unknown[]) ??
    (payload.diffs as unknown[]) ??
    (payload.changes as unknown[]) ??
    (Array.isArray(payload) ? payload : []);
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => {
      const d = item as Record<string, unknown>;
      return {
        section: typeof d.section === "string" ? d.section : undefined,
        before: typeof d.before === "string" ? d.before : "",
        after: typeof d.after === "string" ? d.after : "",
        reason: typeof d.reason === "string" ? d.reason : "",
      };
    })
    .filter((d) => d.before || d.after);
}

/** Normalize recommendation items from an approval payload (defensive). */
function extractRecommendations(payload: Record<string, unknown>): RecommendationItem[] {
  const raw =
    (payload.recommendations as unknown[]) ??
    (payload.match_results as unknown[]) ??
    [];
  if (!Array.isArray(raw)) return [];
  return raw as RecommendationItem[];
}

/** Emit the appropriate rich card for a pending approval. */
async function emitApprovalCard(
  approval: ApprovalResponse,
  pendingType: string,
  sessionId: string
) {
  const chat = useChatStore.getState();
  const type = approval.approval_type || pendingType;

  if (type === "clarification") {
    chat.addMessage({ kind: "clarification", content: approval.title, approval });
    return;
  }

  if (type === "recommendation_review") {
    // Prefer the dedicated endpoint; fall back to the approval payload.
    let items: RecommendationItem[] = [];
    try {
      items = await sessionsApi.getRecommendations(sessionId);
    } catch {
      items = [];
    }
    if (!items || items.length === 0) {
      items = extractRecommendations(approval.payload);
    }
    chat.addMessage({
      kind: "recommendation",
      content: approval.title,
      approval,
      recommendations: items,
    });
    return;
  }

  if (type === "resume_approval") {
    chat.addMessage({
      kind: "resume_diff",
      content: approval.title,
      approval,
      diffs: extractDiffs(approval.payload),
    });
    return;
  }

  // Fallback: generic approval card
  chat.addMessage({ kind: "approval", content: approval.title, approval });
}

function stopTimer() {
  if (timer) {
    clearTimeout(timer);
    timer = null;
  }
  useSessionStore.getState().setPolling(false);
}

async function poll() {
  // Concurrent polling protection: skip if a previous poll is still running
  if (isPollingActive) return;
  isPollingActive = true;

  const sid = useSessionStore.getState().sessionId;
  if (!sid) {
    isPollingActive = false;
    return;
  }

  const chat = useChatStore.getState();

  try {
    const session = await sessionsApi.getSession(sid);

    useSessionStore.getState().setSession({
      sessionId: session.session_id,
      status: session.status,
      currentPhase: session.current_phase,
      progress: session.progress,
      pendingApproval: session.pending_approval,
      tokenUsage: session.token_usage,
    });

    // Update progress card in chat stream
    if (session.progress) {
      chat.updateProgress(session.progress);
    }

    // When entering waiting_approval, fetch approval details and show card
    if (session.status === "waiting_approval" && session.pending_approval) {
      const approvalId = session.pending_approval.id;
      if (approvalShown !== approvalId) {
        approvalShown = approvalId;
        try {
          const approval = await approvalsApi.getApproval(approvalId);
          await emitApprovalCard(
            approval,
            session.pending_approval.type,
            session.session_id
          );
        } catch {
          approvalShown = null; // retry next poll
        }
      }
      stopTimer();
    } else if (TERMINAL_STATUSES.includes(session.status)) {
      // Terminal state: emit result/error message only once
      if (!resultEmitted) {
        resultEmitted = true;
        if (session.status === "completed") {
          chat.addMessage({
            kind: "result",
            content: "流程已完成",
            resultsSummary: session.results_summary,
          });
        } else {
          chat.addMessage({
            kind: "error",
            content: session.status === "failed" ? "执行失败" : "已取消",
          });
        }
      }
      stopTimer();
    }
  } catch {
    // Network error during poll; keep trying
  } finally {
    isPollingActive = false;
  }

  // Schedule next poll using recursive setTimeout (prevents overlap)
  if (useSessionStore.getState().isPolling) {
    timer = setTimeout(poll, POLL_INTERVAL);
  }
}

function startTimer(sessionId?: string) {
  stopTimer();
  resultEmitted = false;
  // Ensure the session store has the id BEFORE the first poll reads it.
  if (sessionId) {
    useSessionStore.getState().setSessionId(sessionId);
  }
  useSessionStore.getState().setPolling(true);
  timer = setTimeout(poll, POLL_INTERVAL);
}

/** Reset singleton state for a brand-new session. */
export function resetSessionPolling() {
  stopTimer();
  approvalShown = null;
  resultEmitted = false;
  isPollingActive = false;
}

export function useSessionPolling() {
  const status = useSessionStore((s) => s.status);
  const isPolling = useSessionStore((s) => s.isPolling);

  const startPolling = useCallback((sessionId?: string) => {
    startTimer(sessionId);
  }, []);

  const stopPolling = useCallback(() => {
    stopTimer();
  }, []);

  return {
    startPolling,
    stopPolling,
    isPolling,
    isActive: status !== null && !TERMINAL_STATUSES.includes(status),
  };
}
