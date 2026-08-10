"use client";

import { useCallback } from "react";
import { ChatStream } from "@/components/chat/ChatStream";
import { ChatInput } from "@/components/chat/ChatInput";
import { ContextPanel } from "@/components/chat/ContextPanel";
import { SessionList, MobileSessionDrawer } from "@/components/chat/SessionList";
import { useChatStore } from "@/stores/chat-store";
import { useSessionStore } from "@/stores/session-store";
import { useSessionPolling, resetSessionPolling } from "@/lib/hooks/useSession";
import * as sessionsApi from "@/lib/api/sessions";

export default function ChatPage() {
  const { sessionId, isSending, addMessage, setSending, setSessionId, startNewConversation } =
    useChatStore();
  const sessionStatus = useSessionStore((s) => s.status);
  const resetSession = useSessionStore((s) => s.reset);
  const { startPolling } = useSessionPolling();

  const handleSend = useCallback(
    async (content: string) => {
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
          });
          setSessionId(session.session_id);
          addMessage({
            kind: "system",
            content: "已收到你的求职意向，Agent 团队开始协作处理...",
          });
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
    [sessionId, sessionStatus, addMessage, setSending, setSessionId, startPolling, startNewConversation, resetSession]
  );

  // Disable input while session is actively running (but allow during approval)
  const isBusy =
    isSending ||
    (sessionStatus !== null &&
      !["completed", "failed", "cancelled", "waiting_approval"].includes(
        sessionStatus
      ));

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
          placeholder={
            sessionStatus === "waiting_approval"
              ? "请先处理上方待审批事项..."
              : undefined
          }
        />
      </div>

      {/* Right context panel */}
      <ContextPanel />
    </div>
  );
}
