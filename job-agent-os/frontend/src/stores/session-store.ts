/** Session store - manages session polling state. */

import { create } from "zustand";
import type { PendingApprovalInfo, SessionProgress, SessionStatus } from "@/types/session";

interface SessionState {
  sessionId: string | null;
  status: SessionStatus | null;
  currentPhase: string | null;
  progress: SessionProgress | null;
  pendingApproval: PendingApprovalInfo | null;
  tokenUsage: Record<string, number>;
  isPolling: boolean;
  setSessionId: (id: string | null) => void;
  setSession: (data: {
    sessionId: string;
    status: SessionStatus;
    currentPhase: string | null;
    progress: SessionProgress | null;
    pendingApproval: PendingApprovalInfo | null;
    tokenUsage: Record<string, number>;
  }) => void;
  setPolling: (v: boolean) => void;
  reset: () => void;
}

export const useSessionStore = create<SessionState>((set) => ({
  sessionId: null,
  status: null,
  currentPhase: null,
  progress: null,
  pendingApproval: null,
  tokenUsage: {},
  isPolling: false,

  setSessionId: (id) => set({ sessionId: id }),

  setSession: (data) =>
    set({
      sessionId: data.sessionId,
      status: data.status,
      currentPhase: data.currentPhase,
      progress: data.progress,
      pendingApproval: data.pendingApproval,
      tokenUsage: data.tokenUsage,
    }),

  setPolling: (v) => set({ isPolling: v }),

  reset: () =>
    set({
      sessionId: null,
      status: null,
      currentPhase: null,
      progress: null,
      pendingApproval: null,
      tokenUsage: {},
      isPolling: false,
    }),
}));
