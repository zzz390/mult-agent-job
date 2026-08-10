"use client";

import { useState } from "react";
import { Check, Loader2, ShieldQuestion, SkipForward, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useChatStore, type ChatMessage } from "@/stores/chat-store";
import * as approvalsApi from "@/lib/api/approvals";
import { useSessionPolling } from "@/lib/hooks/useSession";
import type { ApprovalAction } from "@/types/approval";

export function ApprovalCard({ message }: { message: ChatMessage }) {
  const [feedback, setFeedback] = useState("");
  const [submitting, setSubmitting] = useState<ApprovalAction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const markResolved = useChatStore((s) => s.markResolved);
  const { startPolling } = useSessionPolling();

  const approval = message.approval!;
  const resolved = message.resolved;

  const respond = async (action: ApprovalAction) => {
    setSubmitting(action);
    setError(null);
    try {
      await approvalsApi.respondToApproval(approval.id, {
        action,
        feedback: feedback.trim() || null,
      });
      markResolved(message.id);
      // Resume polling so the graph continues
      startPolling();
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作失败");
    } finally {
      setSubmitting(null);
    }
  };

  return (
    <div className="w-full rounded-xl border border-l-4 border-l-primary bg-card p-4 shadow-sm">
      <div className="mb-2 flex items-center gap-2">
        <ShieldQuestion className="h-4 w-4 text-primary" />
        <span className="text-sm font-semibold">需要你确认</span>
        <span className="ml-auto rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">
          {approval.approval_type}
        </span>
      </div>

      <p className="mb-1 text-sm font-medium">{approval.title}</p>
      {approval.description && (
        <p className="mb-3 text-xs text-muted-foreground">{approval.description}</p>
      )}

      {/* Payload preview */}
      {Object.keys(approval.payload).length > 0 && (
        <pre className="mb-3 max-h-40 overflow-auto rounded-md bg-muted p-3 text-[11px] leading-relaxed text-muted-foreground">
          {JSON.stringify(approval.payload, null, 2)}
        </pre>
      )}

      {resolved ? (
        <div className="rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">
          已处理，Agent 继续执行中...
        </div>
      ) : (
        <>
          {error && <p className="mb-2 text-xs text-destructive">{error}</p>}
          <Textarea
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="反馈意见（可选）..."
            className="mb-3 min-h-[60px]"
          />
          <div className="flex gap-2">
            <Button
              onClick={() => respond("approve")}
              disabled={submitting !== null}
              className="flex-1"
            >
              {submitting === "approve" ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Check className="mr-2 h-4 w-4" />
              )}
              批准
            </Button>
            <Button
              variant="destructive"
              onClick={() => respond("reject")}
              disabled={submitting !== null}
              className="flex-1"
            >
              {submitting === "reject" ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <X className="mr-2 h-4 w-4" />
              )}
              打回
            </Button>
            <Button
              variant="outline"
              onClick={() => respond("skip")}
              disabled={submitting !== null}
            >
              {submitting === "skip" ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <SkipForward className="mr-2 h-4 w-4" />
              )}
              跳过
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
