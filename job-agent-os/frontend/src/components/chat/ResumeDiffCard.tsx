"use client";

import { useState } from "react";
import { Check, FileDiff, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { useChatStore, type ChatMessage } from "@/stores/chat-store";
import * as approvalsApi from "@/lib/api/approvals";
import { useSessionPolling } from "@/lib/hooks/useSession";
import type { ResumeDiffEntry } from "@/types/session";

function DiffRow({ diff }: { diff: ResumeDiffEntry }) {
  return (
    <div className="overflow-hidden rounded-lg border">
      {diff.section && (
        <div className="border-b bg-muted/50 px-3 py-1.5 text-[11px] font-semibold text-muted-foreground">
          {diff.section}
        </div>
      )}
      <div className="grid grid-cols-1 divide-y sm:grid-cols-2 sm:divide-x sm:divide-y-0">
        {/* Before */}
        <div className="p-3">
          <div className="mb-1 flex items-center gap-1 text-[10px] font-bold uppercase text-destructive">
            <X className="h-3 w-3" /> 修改前
          </div>
          <p className="whitespace-pre-wrap rounded-md bg-destructive/5 p-2 text-xs leading-relaxed text-muted-foreground line-through decoration-destructive/60">
            {diff.before}
          </p>
        </div>
        {/* After */}
        <div className="p-3">
          <div className="mb-1 flex items-center gap-1 text-[10px] font-bold uppercase text-emerald-600">
            <Check className="h-3 w-3" /> 修改后
          </div>
          <p className="whitespace-pre-wrap rounded-md bg-emerald-500/5 p-2 text-xs leading-relaxed">
            {diff.after}
          </p>
        </div>
      </div>
      {/* Reason */}
      <div className="border-t bg-muted/30 px-3 py-2 text-[11px] text-muted-foreground">
        <span className="font-semibold text-foreground">修改理由：</span>
        {diff.reason}
      </div>
    </div>
  );
}

export function ResumeDiffCard({ message }: { message: ChatMessage }) {
  const diffs = message.diffs ?? [];
  const approval = message.approval;
  const readOnly = message.readOnly;
  const resolved = message.resolved;

  const [feedback, setFeedback] = useState("");
  const [submitting, setSubmitting] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const markResolved = useChatStore((s) => s.markResolved);
  const { startPolling } = useSessionPolling();

  const respond = async (action: "approve" | "reject") => {
    if (!approval) return;
    setSubmitting(action);
    setError(null);
    try {
      await approvalsApi.respondToApproval(approval.id, {
        action,
        feedback: feedback.trim() || null,
      });
      markResolved(message.id);
      startPolling();
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作失败");
    } finally {
      setSubmitting(null);
    }
  };

  return (
    <div className="w-full rounded-xl border border-l-4 border-l-violet-500 bg-card p-4 shadow-sm">
      <div className="mb-2 flex items-center gap-2">
        <FileDiff className="h-4 w-4 text-violet-500" />
        <span className="text-sm font-semibold">简历优化对比</span>
        <Badge variant="secondary" className="ml-auto">
          {diffs.length} 处修改
        </Badge>
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        Agent 已针对目标岗位优化你的简历，请审阅以下修改（不会捏造经历）。
      </p>

      <div className="mb-3 space-y-3">
        {diffs.length === 0 ? (
          <p className="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
            暂无修改对比数据。
          </p>
        ) : (
          diffs.map((d, i) => <DiffRow key={i} diff={d} />)
        )}
      </div>

      {resolved ? (
        <div className="rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">
          已处理，Agent 继续执行中...
        </div>
      ) : (
        !readOnly &&
        approval && (
          <>
            {error && <p className="mb-2 text-xs text-destructive">{error}</p>}
            <Textarea
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder="修改意见（可选），如：项目经历描述再精简一些..."
              className="mb-3 min-h-[56px]"
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
                确认使用
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
                打回重做
              </Button>
            </div>
          </>
        )
      )}
    </div>
  );
}
