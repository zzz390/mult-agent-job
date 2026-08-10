"use client";

import { Check, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { SessionProgress } from "@/types/session";

/** Canonical pipeline step order with display labels */
export const PIPELINE_STEPS: { key: string; label: string }[] = [
  { key: "intent", label: "意图解析" },
  { key: "search", label: "岗位搜索" },
  { key: "web_search", label: "官网搜索" },
  { key: "parse", label: "JD解析" },
  { key: "match", label: "匹配评分" },
  { key: "resume", label: "简历优化" },
  { key: "interview", label: "面试准备" },
  { key: "tracker", label: "投递创建" },
];

function stepStatus(
  stepKey: string,
  progress: SessionProgress
): "done" | "active" | "pending" {
  if (progress.completed_steps.includes(stepKey)) return "done";
  if (progress.current_step === stepKey) return "active";
  return "pending";
}

export function ProgressCard({ progress }: { progress: SessionProgress }) {
  return (
    <div className="w-full rounded-xl border border-l-4 border-l-primary bg-card p-4 shadow-sm">
      <div className="mb-3 text-sm font-semibold text-card-foreground">
        Agent 执行进度
      </div>
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
