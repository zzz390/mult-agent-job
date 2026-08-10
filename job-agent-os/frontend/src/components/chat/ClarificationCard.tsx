"use client";

import { useState } from "react";
import { HelpCircle, Loader2, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useChatStore, type ChatMessage } from "@/stores/chat-store";
import { useSessionStore } from "@/stores/session-store";
import * as sessionsApi from "@/lib/api/sessions";
import { useSessionPolling } from "@/lib/hooks/useSession";

export function ClarificationCard({ message }: { message: ChatMessage }) {
  const [value, setValue] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const markResolved = useChatStore((s) => s.markResolved);
  const sessionId = useSessionStore((s) => s.sessionId);
  const { startPolling } = useSessionPolling();

  const resolved = message.resolved;

  const submit = async () => {
    if (!value.trim() || !sessionId) return;
    setSubmitting(true);
    setError(null);
    try {
      await sessionsApi.sendMessage(sessionId, {
        content: value.trim(),
        message_type: "clarification",
      });
      markResolved(message.id);
      // Add user's clarification as a user message
      useChatStore.getState().addMessage({ kind: "user", content: value.trim() });
      // Resume polling
      startPolling();
    } catch (e) {
      setError(e instanceof Error ? e.message : "提交失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="w-full rounded-xl border border-l-4 border-l-amber-500 bg-card p-4 shadow-sm">
      <div className="mb-2 flex items-center gap-2">
        <HelpCircle className="h-4 w-4 text-amber-500" />
        <span className="text-sm font-semibold">需要补充信息</span>
      </div>
      <p className="mb-3 text-sm text-muted-foreground">{message.content}</p>

      {resolved ? (
        <div className="rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">
          已补充信息，Agent 继续执行中...
        </div>
      ) : (
        <>
          {error && <p className="mb-2 text-xs text-destructive">{error}</p>}
          <div className="flex gap-2">
            <Input
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="补充你的求职意向，如：郑州、Java方向..."
              onKeyDown={(e) => e.key === "Enter" && submit()}
              disabled={submitting}
            />
            <Button onClick={submit} disabled={submitting || !value.trim()} size="icon">
              {submitting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
