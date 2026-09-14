/** useSession hook - keeps session status and chat progress cards in sync.
 *
 * SSE provides low-latency updates, while a lightweight poll runs alongside
 * it.  The latter is important when an intermediary buffers a long-lived SSE
 * response instead of forwarding its chunks promptly.
 */

"use client";

import { useCallback } from "react";
import * as sessionsApi from "@/lib/api/sessions";
import * as approvalsApi from "@/lib/api/approvals";
import { useChatStore } from "@/stores/chat-store";
import { useSessionStore } from "@/stores/session-store";
import type { ApprovalResponse } from "@/types/approval";
import type { RecommendationItem } from "@/types/job";
import type {
  ResumeDiffEntry,
  SessionStatus,
  SessionStreamEvent,
} from "@/types/session";

const POLL_INTERVAL = 2000;
const TERMINAL_STATUSES: SessionStatus[] = ["completed", "failed", "cancelled"];

// Module-level singleton state
let timer: ReturnType<typeof setTimeout> | null = null;
let streamAbort: AbortController | null = null;
let approvalShown: string | null = null;
let clarificationShown: string | null = null;
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
  if (streamAbort) {
    streamAbort.abort();
    streamAbort = null;
  }
  useSessionStore.getState().setPolling(false);
}

/** Schedule the polling safety net without allowing overlapping requests. */
function schedulePoll(delay = POLL_INTERVAL) {
  if (timer) {
    clearTimeout(timer);
  }
  timer = setTimeout(() => {
    timer = null;
    void poll();
  }, delay);
}

/**
 * Apply the useful portion of an SSE frame immediately.  A full REST sync
 * still follows for approval details, token usage and result summaries.
 */
function applyStreamEvent(event: SessionStreamEvent) {
  const sessionState = useSessionStore.getState();
  const sessionId = sessionState.sessionId;
  if (!sessionId) return;

  const nextStatus = event.status ?? sessionState.status ?? "running";
  const nextPhase =
    event.phase === undefined ? sessionState.currentPhase : event.phase;
  const nextProgress = event.progress ?? sessionState.progress;

  if (nextStatus) {
    sessionState.setSession({
      sessionId,
      status: nextStatus,
      currentPhase: nextPhase,
      progress: nextProgress,
      pendingApproval: sessionState.pendingApproval,
      tokenUsage: sessionState.tokenUsage,
    });
  }

  if (event.progress) {
    useChatStore.getState().updateProgress(event.progress);
  }
}

async function syncSession() {
  // Concurrent update protection: skip if an SSE event and fallback poll race.
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

    // A retry/new conversation may have replaced the store while this request
    // was in flight.  Never let an old session snapshot overwrite the new
    // chat's live progress.
    if (useSessionStore.getState().sessionId !== sid) return;

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
    } else if (session.status === "waiting_input") {
      const question = session.results_summary.clarification_question;
      const content =
        typeof question === "string" && question.trim()
          ? question
          : "请补充您的求职意向信息。";
      const marker = `${session.session_id}:${content}`;
      if (clarificationShown !== marker) {
        clarificationShown = marker;
        chat.addMessage({ kind: "clarification", content });
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

}

async function poll() {
  await syncSession();

  // Keep a low-frequency safety net even while SSE remains connected.
  if (useSessionStore.getState().isPolling) {
    schedulePoll();
  }
}

async function connectStream(sessionId: string, controller: AbortController) {
  try {
    await sessionsApi.streamSession(
      sessionId,
      async (event) => {
        applyStreamEvent(event);
        await syncSession();
      },
      controller.signal
    );
  } catch (error) {
    if (controller.signal.aborted) return;
  }

  // A healthy backend closes at a waiting/terminal state, which syncSession
  // handles by stopping.  If the stream failed or was buffered/closed early,
  // switch to the polling path immediately rather than waiting for a timeout.
  if (useSessionStore.getState().isPolling && !controller.signal.aborted) {
    if (streamAbort === controller) {
      streamAbort = null;
    }
    schedulePoll(0);
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
  const sid = sessionId ?? useSessionStore.getState().sessionId;
  if (!sid) {
    stopTimer();
    return;
  }
  const controller = new AbortController();
  streamAbort = controller;
  // Do not wait for the first stream frame before showing the current Agent.
  void syncSession();
  // Polling runs as a safety net from the beginning, rather than only after
  // SSE closes. This makes progress visible through buffering proxies too.
  schedulePoll();
  void connectStream(sid, controller);
}

/** Reset singleton state for a brand-new session. */
export function resetSessionPolling() {
  stopTimer();
  approvalShown = null;
  clarificationShown = null;
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
