"use client";

import { useCallback } from "react";
import { ChatStream } from "@/components/chat/ChatStream";
import { ChatInput, type ChatSendOptions } from "@/components/chat/ChatInput";
import { ContextPanel } from "@/components/chat/ContextPanel";
import { SessionList, MobileSessionDrawer } from "@/components/chat/SessionList";
import { useChatStore } from "@/stores/chat-store";
import { useSessionStore } from "@/stores/session-store";
import { useSessionPolling, resetSessionPolling } from "@/lib/hooks/useSession";
import * as sessionsApi from "@/lib/api/sessions";
import type { SessionProgress } from "@/types/session";

export default function ChatPage() {
  const { sessionId, isSending, addMessage, setSending, setSessionId, startNewConversation, updateProgress } =
    useChatStore();
  const sessionStatus = useSessionStore((s) => s.status);
  const resetSession = useSessionStore((s) => s.reset);
  const setSession = useSessionStore((s) => s.setSession);
  const { startPolling } = useSessionPolling();

  const handleSend = useCallback(
    async (content: string, sendOptions?: ChatSendOptions) => {
      setSending(true);

      try {
        // If no active session, create one with the intent
        if (!sessionId || sessionStatus === "completed" || sessionStatus === "failed" || sessionStatus === "cancelled") {
          // Start fresh: directly set messages to only the new user message
          resetSession();
          resetSessionPolling();
          startNewConversation({ kind: "user", content });

          const session = await sessionsApi.createSession({
            intent: content,
            mode: "full",
            // Omit options when no platform was selected so the backend keeps
            // its official-site-first default search strategy.
            options:
              sendOptions?.platforms && sendOptions.platforms.length > 0
                ? { platforms: sendOptions.platforms }
                : undefined,
          });

          // The create response already contains the first live state
          // (normally the supervisor Agent).  Render it immediately instead
          // of waiting for an SSE chunk, which can be delayed by a proxy.
          setSessionId(session.session_id);
          setSession({
            sessionId: session.session_id,
            status: session.status,
            currentPhase: session.current_phase,
            progress: session.progress,
            pendingApproval: session.pending_approval,
            tokenUsage: session.token_usage,
          });

          const initialProgress: SessionProgress = session.progress ?? {
            completed_steps: [],
            current_step: session.current_phase,
            pending_steps: [],
            active_agent: session.current_phase,
            active_agent_status:
              session.status === "running" ? "running" : null,
          };
          updateProgress(initialProgress);

          // Pass the id so the poller reads a non-null sessionId on first tick
          startPolling(session.session_id);
        } else {
          // Otherwise send as a follow-up message to the active session
          addMessage({ kind: "user", content });
          await sessionsApi.sendMessage(sessionId, {
            content,
            message_type: "text",
          });
          startPolling(sessionId);
        }
      } catch (e) {
        addMessage({
          kind: "error",
          content: e instanceof Error ? e.message : "发送失败，请重试",
        });
      } finally {
        setSending(false);
      }
    },
    [
      sessionId,
      sessionStatus,
      // `sendOptions` is an invocation argument, not a captured value.
      addMessage,
      setSending,
      setSessionId,
      setSession,
      updateProgress,
      startPolling,
      startNewConversation,
      resetSession,
    ]
  );

  // Keep input available when the workflow explicitly asks for clarification.
  const isBusy =
    isSending ||
    (sessionStatus !== null &&
      !["completed", "failed", "cancelled", "waiting_approval", "waiting_input"].includes(
        sessionStatus
      ));
  const platformSelectionAvailable =
    !sessionId ||
    sessionStatus === "completed" ||
    sessionStatus === "failed" ||
    sessionStatus === "cancelled";

  // Retry: reset session so the next send starts a fresh session
  const handleRetry = useCallback(() => {
    resetSessionPolling();
    resetSession();
  }, [resetSession]);

  return (
    <div className="flex h-full">
      {/* Left session list */}
      <SessionList />

      {/* Main chat column */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Mobile-only top bar with session list trigger */}
        <div className="flex items-center gap-2 border-b bg-card px-3 py-2 md:hidden">
          <MobileSessionDrawer />
          <span className="text-sm font-semibold">智能求职助手</span>
        </div>
        <ChatStream onRetry={handleRetry} />
        <ChatInput
          onSend={handleSend}
          disabled={isBusy}
          platformSelectionAvailable={platformSelectionAvailable}
          placeholder={
            sessionStatus === "waiting_approval"
              ? "请先处理上方待审批事项..."
              : sessionStatus === "waiting_input"
                ? "请补充上方所需的信息..."
              : undefined
          }
        />
      </div>

      {/* Right context panel */}
      <ContextPanel />
    </div>
  );
}
