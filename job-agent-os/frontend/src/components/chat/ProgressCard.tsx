"use client";

import { Check, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { SessionProgress } from "@/types/session";

/**
 * User-visible workflow stages.  Website discovery and JD parsing now run
 * inside the search Agent, while application creation runs inside interview;
 * they must not appear as permanently pending standalone stages.
 */
export const PIPELINE_STEPS: { key: string; label: string }[] = [
  { key: "intent", label: "意图解析" },
  { key: "search", label: "岗位搜索与 JD 解析" },
  { key: "match", label: "匹配评分" },
  { key: "resume", label: "简历优化" },
  { key: "interview", label: "面试准备与投递" },
];

export const AGENT_LABELS: Record<string, string> = {
  supervisor: "调度 Agent",
  intent: "意图解析 Agent",
  search: "岗位搜索 Agent",
  web_search: "官网搜索 Agent",
  parse: "JD 解析 Agent",
  match: "匹配评分 Agent",
  resume: "简历优化 Agent",
  interview: "面试准备 Agent",
  tracker: "投递跟踪 Agent",
};

export function agentLabel(agent: string | null | undefined) {
  return agent ? (AGENT_LABELS[agent] ?? `${agent} Agent`) : null;
}

function stepStatus(
  stepKey: string,
  progress: SessionProgress
): "done" | "active" | "pending" {
  if (progress.current_step === stepKey) return "active";
  if (progress.completed_steps.includes(stepKey)) return "done";
  return "pending";
}

export function ProgressCard({ progress }: { progress: SessionProgress }) {
  const activeAgent = agentLabel(progress.active_agent ?? progress.current_step);
  const metrics = [
    typeof progress.items_found === "number"
      ? `已发现 ${progress.items_found} 条`
      : null,
    typeof progress.items_saved === "number"
      ? `已入库 ${progress.items_saved} 条`
      : null,
  ].filter((item): item is string => Boolean(item));
  const lastActivity = progress.last_activity_at
    ? new Date(progress.last_activity_at)
    : null;
  const lastActivityText =
    lastActivity && !Number.isNaN(lastActivity.getTime())
      ? `最近活动 ${lastActivity.toLocaleTimeString("zh-CN", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        })}`
      : null;

  return (
    <div className="w-full rounded-xl border border-l-4 border-l-primary bg-card p-4 shadow-sm">
      <div aria-live="polite" className="mb-1 flex items-center gap-2 text-sm font-semibold text-card-foreground">
        {activeAgent && <Loader2 className="h-4 w-4 animate-spin text-primary" />}
        {activeAgent ? `${activeAgent} 正在工作` : "Agent 执行进度"}
      </div>
      {activeAgent && (
        <p className="mb-3 text-xs text-muted-foreground">
          当前执行阶段会实时更新；岗位搜索包含官网检索和 JD 解析。
        </p>
      )}
      {(progress.activity_message || metrics.length > 0 || lastActivityText) && (
        <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md bg-muted/60 px-3 py-2 text-xs text-muted-foreground">
          {progress.activity_message && (
            <span className="font-medium text-foreground">
              {progress.activity_message}
            </span>
          )}
          {metrics.map((metric) => (
            <span key={metric}>{metric}</span>
          ))}
          {lastActivityText && <span>{lastActivityText}</span>}
        </div>
      )}
      <div className="flex items-center gap-1 overflow-x-auto pb-1">
        {PIPELINE_STEPS.map((step, idx) => {
          const status = stepStatus(step.key, progress);
          return (
            <div key={step.key} className="flex items-center">
              {idx > 0 && (
                <div
                  className={cn(
                    "mx-1 h-0.5 w-4 shrink-0 sm:w-6",
                    status === "pending" ? "bg-muted" : "bg-primary"
                  )}
                />
              )}
              <div className="flex shrink-0 flex-col items-center gap-1.5">
                <div
                  className={cn(
                    "flex h-7 w-7 items-center justify-center rounded-full border-2 text-xs font-bold transition-colors",
                    status === "done" &&
                      "border-emerald-500 bg-emerald-500 text-white",
                    status === "active" &&
                      "animate-pulse border-primary bg-primary text-primary-foreground",
                    status === "pending" &&
                      "border-muted-foreground/30 bg-muted text-muted-foreground"
                  )}
                >
                  {status === "done" ? (
                    <Check className="h-3.5 w-3.5" />
                  ) : status === "active" ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    idx + 1
                  )}
                </div>
                <span
                  className={cn(
                    "whitespace-nowrap text-[10px] font-medium",
                    status === "active"
                      ? "text-primary"
                      : status === "done"
                        ? "text-emerald-600"
                        : "text-muted-foreground"
                  )}
                >
                  {step.label}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
