"use client";

import { Activity, AlertCircle, Coins, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { useSessionStore } from "@/stores/session-store";
import { useAuthStore } from "@/stores/auth-store";
import { agentLabel, PIPELINE_STEPS } from "./ProgressCard";

const TOKEN_BUDGET = 100000;

export function ContextPanel() {
  const { status, currentPhase, progress, pendingApproval, tokenUsage } = useSessionStore();
  const tokenBudget = useAuthStore((s) => s.user?.token_budget_daily ?? TOKEN_BUDGET);
  const activeAgent =
    status === "running"
      ? agentLabel(progress?.active_agent ?? progress?.current_step ?? currentPhase)
      : null;

  const totalTokens =
    tokenUsage.total_tokens ??
    Object.values(tokenUsage).reduce(
      (sum, v) => (typeof v === "number" ? sum + v : sum),
      0
    );
  const tokenPercent = Math.min(100, Math.round((totalTokens / tokenBudget) * 100));

  return (
    <aside className="hidden w-80 shrink-0 flex-col gap-5 overflow-y-auto border-l bg-card p-4 xl:flex">
      {/* Current Agent */}
      <section className="rounded-lg border border-primary/20 bg-primary/5 p-3">
        <div className="mb-1 flex items-center gap-2 text-sm font-semibold">
          <Activity className="h-4 w-4 text-primary" />
          当前执行
        </div>
        {activeAgent ? (
          <div className="flex items-center gap-2 text-sm text-primary">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span>{activeAgent} 正在工作</span>
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">当前没有运行中的 Agent</p>
        )}
      </section>

      {/* Execution progress */}
      <section>
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
          <Activity className="h-4 w-4 text-primary" />
          执行过程
        </div>
        {progress ? (
          <ol className="space-y-2">
            {PIPELINE_STEPS.map((step) => {
              const done = progress.completed_steps.includes(step.key);
              const active = progress.current_step === step.key;
              return (
                <li key={step.key} className="flex items-center gap-2 text-sm">
                  <span
                    className={cn(
                      "flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold",
                      active && "animate-pulse bg-primary text-primary-foreground",
                      done && !active && "bg-emerald-500 text-white",
                      !done && !active && "bg-muted text-muted-foreground"
                    )}
                  >
                    {active ? "…" : done ? "✓" : "•"}
                  </span>
                  <span
                    className={cn(
                      active && "font-medium text-primary",
                      done && !active && "text-emerald-600",
                      !done && !active && "text-muted-foreground"
                    )}
                  >
                    {step.label}
                  </span>
                </li>
              );
            })}
          </ol>
        ) : (
          <p className="text-xs text-muted-foreground">暂无进行中的任务</p>
        )}
      </section>

      {/* Pending approval */}
      <section>
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
          <AlertCircle className="h-4 w-4 text-amber-500" />
          待审批
        </div>
        {pendingApproval ? (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 dark:border-amber-900 dark:bg-amber-950">
            <Badge variant="warning" className="mb-1.5">
              {pendingApproval.type}
            </Badge>
            <p className="text-xs font-medium">{pendingApproval.title}</p>
            <p className="mt-1 text-[11px] text-muted-foreground">
              请在左侧对话中处理该审批
            </p>
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">暂无待审批事项</p>
        )}
      </section>

      {/* Token usage */}
      <section>
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
          <Coins className="h-4 w-4 text-primary" />
          Token 用量
        </div>
        <div className="space-y-2">
          <div className="flex items-baseline justify-between">
            <span className="text-lg font-bold">{totalTokens.toLocaleString()}</span>
            <span className="text-xs text-muted-foreground">
              / {tokenBudget.toLocaleString()}
            </span>
          </div>
          <Progress value={tokenPercent} />
          <p className="text-[11px] text-muted-foreground">
            已使用 {tokenPercent}% 会话预算
          </p>
        </div>
      </section>

      {/* Session status */}
      {status && (
        <section className="mt-auto border-t pt-4">
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">会话状态</span>
            <Badge
              variant={
                status === "completed"
                  ? "success"
                  : status === "failed"
                    ? "destructive"
                    : status === "waiting_approval"
                      ? "warning"
                      : "secondary"
              }
            >
              {status}
            </Badge>
          </div>
        </section>
      )}
    </aside>
  );
}
