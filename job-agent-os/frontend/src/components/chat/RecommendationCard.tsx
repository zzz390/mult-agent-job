"use client";

import { useState } from "react";
import {
  Briefcase,
  Check,
  ChevronDown,
  Loader2,
  RefreshCcw,
  Sparkles,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useChatStore, type ChatMessage } from "@/stores/chat-store";
import { useSessionStore } from "@/stores/session-store";
import * as sessionsApi from "@/lib/api/sessions";
import * as approvalsApi from "@/lib/api/approvals";
import { useSessionPolling } from "@/lib/hooks/useSession";
import type { RecommendationItem } from "@/types/job";

type ItemDecision = "accept" | "reject" | null;

function scoreColor(score: number) {
  if (score >= 80) return "text-emerald-600";
  if (score >= 60) return "text-amber-600";
  return "text-muted-foreground";
}

function RecommendationItemRow({
  item,
  decision,
  readOnly,
  onDecide,
}: {
  item: RecommendationItem;
  decision: ItemDecision;
  readOnly?: boolean;
  onDecide: (jobId: string, d: ItemDecision) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const job = item.job;

  return (
    <div
      className={cn(
        "rounded-lg border transition-colors",
        decision === "accept" && "border-emerald-300 bg-emerald-50/50 dark:border-emerald-900 dark:bg-emerald-950/30",
        decision === "reject" && "border-destructive/30 bg-destructive/5 opacity-70"
      )}
    >
      {/* Header row */}
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-3 p-3 text-left"
      >
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <Briefcase className="h-4 w-4 text-primary" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-semibold">{job.title}</span>
            <span className={cn("shrink-0 text-sm font-bold", scoreColor(item.match_score))}>
              {Math.round(item.match_score)}分
            </span>
          </div>
          <p className="truncate text-xs text-muted-foreground">
            {job.company}
            {job.location ? ` · ${job.location}` : ""}
            {job.salary_range ? ` · ${job.salary_range}` : ""}
          </p>
        </div>
        <ChevronDown
          className={cn("h-4 w-4 shrink-0 text-muted-foreground transition-transform", expanded && "rotate-180")}
        />
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t px-3 pb-3 pt-2">
          <p className="mb-2 text-xs leading-relaxed text-muted-foreground">
            <Sparkles className="mr-1 inline h-3 w-3 text-primary" />
            {item.recommendation_reason}
          </p>
          {item.matched_skills.length > 0 && (
            <div className="mb-2 flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] text-muted-foreground">匹配技能:</span>
              {item.matched_skills.map((s) => (
                <Badge key={s} variant="success" className="px-1.5 py-0 text-[10px]">
                  {s}
                </Badge>
              ))}
            </div>
          )}
          {item.missing_skills.length > 0 && (
            <div className="mb-2 flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] text-muted-foreground">欠缺技能:</span>
              {item.missing_skills.map((s) => (
                <Badge key={s} variant="secondary" className="px-1.5 py-0 text-[10px]">
                  {s}
                </Badge>
              ))}
            </div>
          )}
          {item.risk_factors.length > 0 && (
            <div className="mb-2 flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] text-muted-foreground">风险因素:</span>
              {item.risk_factors.map((s) => (
                <Badge key={s} variant="warning" className="px-1.5 py-0 text-[10px]">
                  {s}
                </Badge>
              ))}
            </div>
          )}
          {/* Structured JD detail */}
          {job.structured_jd && Object.keys(job.structured_jd).length > 0 && (
            <pre className="mb-2 max-h-36 overflow-auto rounded-md bg-muted p-2 text-[10px] leading-relaxed text-muted-foreground">
              {JSON.stringify(job.structured_jd, null, 2)}
            </pre>
          )}
          {job.source_url && (
            <a
              href={job.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[11px] text-primary underline-offset-2 hover:underline"
            >
              查看原始链接 ↗
            </a>
          )}
        </div>
      )}

      {/* Per-item actions */}
      {!readOnly && (
        <div className="flex items-center gap-2 border-t px-3 py-2">
          <Button
            size="sm"
            variant={decision === "accept" ? "default" : "outline"}
            className="h-7 flex-1 text-xs"
            onClick={() => onDecide(job.id, decision === "accept" ? null : "accept")}
          >
            <Check className="mr-1 h-3 w-3" /> 接受
          </Button>
          <Button
            size="sm"
            variant={decision === "reject" ? "destructive" : "outline"}
            className="h-7 flex-1 text-xs"
            onClick={() => onDecide(job.id, decision === "reject" ? null : "reject")}
          >
            <X className="mr-1 h-3 w-3" /> 拒绝
          </Button>
        </div>
      )}
    </div>
  );
}

export function RecommendationCard({ message }: { message: ChatMessage }) {
  const items = message.recommendations ?? [];
  const approval = message.approval;
  const readOnly = message.readOnly;
  const resolved = message.resolved;

  const [decisions, setDecisions] = useState<Record<string, ItemDecision>>({});
  const [feedback, setFeedback] = useState("");
  const [submitting, setSubmitting] = useState<"accept" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const markResolved = useChatStore((s) => s.markResolved);
  const sessionId = useSessionStore((s) => s.sessionId);
  const { startPolling } = useSessionPolling();

  const decide = (jobId: string, d: ItemDecision) => {
    setDecisions((prev) => ({ ...prev, [jobId]: d }));
  };

  /** Send per-job feedback then respond to the approval to resume the graph. */
  const submit = async (mode: "accept" | "reject") => {
    if (!sessionId) return;
    setSubmitting(mode);
    setError(null);
    try {
      if (mode === "accept") {
        // Accept all (or only the accepted ones if user made explicit choices)
        const hasExplicit = Object.values(decisions).some((d) => d !== null);
        for (const item of items) {
          const d = hasExplicit ? decisions[item.job.id] : "accept";
          if (d === "reject") continue; // skip explicitly rejected
          await sessionsApi.submitRecommendationFeedback(sessionId, {
            job_id: item.job.id,
            action: "accept",
          });
        }
      }
      // Respond to the approval to resume the graph
      if (approval) {
        await approvalsApi.respondToApproval(approval.id, {
          action: mode === "accept" ? "approve" : "reject",
          feedback: feedback.trim() || (mode === "reject" ? "重新匹配" : null),
        });
      }
      markResolved(message.id);
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
        <Sparkles className="h-4 w-4 text-primary" />
        <span className="text-sm font-semibold">岗位推荐结果</span>
        <Badge variant="secondary" className="ml-auto">
          {items.length} 个岗位
        </Badge>
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        以下是 Agent 为你匹配并排序的岗位，请确认或调整推荐结果。
      </p>

      <div className="mb-3 space-y-2">
        {items.length === 0 ? (
          <p className="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
            暂无推荐数据，可等待匹配完成后查看。
          </p>
        ) : (
          items.map((item) => (
            <RecommendationItemRow
              key={item.job.id}
              item={item}
              decision={decisions[item.job.id] ?? null}
              readOnly={readOnly || resolved}
              onDecide={decide}
            />
          ))
        )}
      </div>

      {resolved ? (
        <div className="rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">
          已处理，Agent 继续执行中...
        </div>
      ) : (
        !readOnly && (
          <>
            {error && <p className="mb-2 text-xs text-destructive">{error}</p>}
            <Textarea
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder="反馈意见（可选），如：更偏向国企、薪资期望 8k 以上..."
              className="mb-3 min-h-[56px]"
            />
            <div className="flex gap-2">
              <Button
                onClick={() => submit("accept")}
                disabled={submitting !== null || items.length === 0}
                className="flex-1"
              >
                {submitting === "accept" ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Check className="mr-2 h-4 w-4" />
                )}
                接受全部
              </Button>
              <Button
                variant="destructive"
                onClick={() => submit("reject")}
                disabled={submitting !== null}
                className="flex-1"
              >
                {submitting === "reject" ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCcw className="mr-2 h-4 w-4" />
                )}
                拒绝重新匹配
              </Button>
            </div>
          </>
        )
      )}
    </div>
  );
}
