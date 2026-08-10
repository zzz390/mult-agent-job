/** Chat store - manages the message stream for the current conversation. */

import { create } from "zustand";
import type { ApprovalResponse } from "@/types/approval";
import type { RecommendationItem } from "@/types/job";
import type {
  InterviewQuestion,
  ResumeDiffEntry,
  SessionProgress,
} from "@/types/session";

export type ChatMessageKind =
  | "user"
  | "system"
  | "progress"
  | "clarification"
  | "approval"
  | "recommendation"
  | "resume_diff"
  | "interview"
  | "result"
  | "error";

export interface ChatMessage {
  id: string;
  kind: ChatMessageKind;
  content: string;
  timestamp: number;
  /** For progress messages */
  progress?: SessionProgress;
  /** For approval / clarification messages */
  approval?: ApprovalResponse;
  /** For recommendation messages */
  recommendations?: RecommendationItem[];
  /** For resume_diff messages */
  diffs?: ResumeDiffEntry[];
  /** For interview messages */
  questions?: InterviewQuestion[];
  /** For result messages (session results_summary) */
  resultsSummary?: Record<string, unknown>;
  /** Whether an interactive card has been actioned */
  resolved?: boolean;
  /** Read-only mode (history view): cards cannot be actioned */
  readOnly?: boolean;
}

interface ChatState {
  sessionId: string | null;
  messages: ChatMessage[];
  isSending: boolean;
  setSessionId: (id: string | null) => void;
  addMessage: (msg: Omit<ChatMessage, "id" | "timestamp">) => string;
  updateProgress: (progress: SessionProgress) => void;
  markResolved: (id: string) => void;
  setSending: (v: boolean) => void;
  clear: () => void;
  startNewConversation: (msg: Omit<ChatMessage, "id" | "timestamp">) => void;
}

let msgCounter = 0;
function genId() {
  msgCounter += 1;
  return `msg-${Date.now()}-${msgCounter}`;
}

export const useChatStore = create<ChatState>((set, get) => ({
  sessionId: null,
  messages: [],
  isSending: false,

  setSessionId: (id) => set({ sessionId: id }),

  addMessage: (msg) => {
    const id = genId();
    set((state) => ({
      messages: [...state.messages, { ...msg, id, timestamp: Date.now() }],
    }));
    return id;
  },

  updateProgress: (progress) => {
    const { messages } = get();
    // Update the latest progress card if it exists, otherwise add one
    const lastProgressIdx = [...messages]
      .map((m, i) => ({ m, i }))
      .filter(({ m }) => m.kind === "progress")
      .pop()?.i;

    if (lastProgressIdx !== undefined) {
      set((state) => {
        const updated = [...state.messages];
        updated[lastProgressIdx] = { ...updated[lastProgressIdx], progress };
        return { messages: updated };
      });
    } else {
      get().addMessage({ kind: "progress", content: "Agent 正在执行...", progress });
    }
  },

  markResolved: (id) =>
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === id ? { ...m, resolved: true } : m
      ),
    })),

  setSending: (v) => set({ isSending: v }),

  clear: () => set({ sessionId: null, messages: [], isSending: false }),

  startNewConversation: (msg) => {
    const id = genId();
    set({
      sessionId: null,
      messages: [{ ...msg, id, timestamp: Date.now() }],
    });
  },
}));
