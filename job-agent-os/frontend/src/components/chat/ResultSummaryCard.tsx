"use client";

import { PartyPopper } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import type { ChatMessage } from "@/stores/chat-store";

function StatChip({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex flex-col items-center rounded-lg bg-muted/60 px-3 py-2">
      <span className="text-base font-bold text-primary">{value}</span>
      <span className="text-[10px] text-muted-foreground">{label}</span>
    </div>
  );
}

export function ResultSummaryCard({ message }: { message: ChatMessage }) {
  const summary = message.resultsSummary ?? {};
  const matchCount =
    typeof summary.match_results_count === "number" ? summary.match_results_count : null;
  const appCount =
    typeof summary.applications_count === "number" ? summary.applications_count : null;

  return (
    <div className="w-full rounded-xl border border-l-4 border-l-emerald-500 bg-card p-4 shadow-sm">
      <div className="mb-2 flex items-center gap-2">
        <PartyPopper className="h-4 w-4 text-emerald-500" />
        <span className="text-sm font-semibold">{message.content}</span>
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        全部流程已完成，你可以查看投递看板、岗位列表或面试准备。
      </p>

      {(matchCount !== null || appCount !== null) && (
        <div className="mb-3 flex gap-2">
          {matchCount !== null && <StatChip label="匹配岗位" value={matchCount} />}
          {appCount !== null && <StatChip label="创建投递" value={appCount} />}
        </div>
      )}

      <div className="flex gap-2">
        <Button asChild size="sm" variant="outline">
          <Link href="/kanban">查看看板</Link>
        </Button>
        <Button asChild size="sm" variant="outline">
          <Link href="/jobs">查看岗位</Link>
        </Button>
        <Button asChild size="sm" variant="outline">
          <Link href="/interview">面试准备</Link>
        </Button>
      </div>
    </div>
  );
}
