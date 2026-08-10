"use client";

import { useDroppable } from "@dnd-kit/core";
import { cn } from "@/lib/utils";
import { KanbanCard } from "./KanbanCard";
import type { ApplicationResponse, ApplicationStatus } from "@/types/application";
import type { JobResponse } from "@/types/job";

const COLUMN_ACCENT: Record<string, string> = {
  pending: "bg-slate-400",
  applied: "bg-blue-500",
  written_test: "bg-indigo-500",
  round1: "bg-violet-500",
  round2: "bg-purple-500",
  hr_interview: "bg-fuchsia-500",
  offer: "bg-emerald-500",
  rejected: "bg-rose-400",
};

interface KanbanColumnProps {
  status: ApplicationStatus;
  label: string;
  applications: ApplicationResponse[];
  jobsMap: Record<string, JobResponse>;
}

export function KanbanColumn({ status, label, applications, jobsMap }: KanbanColumnProps) {
  const { setNodeRef, isOver } = useDroppable({ id: status });

  return (
    <div
      ref={setNodeRef}
      className={cn(
        "flex w-64 shrink-0 flex-col rounded-xl border bg-muted/30 transition-colors",
        isOver && "border-primary bg-primary/5 ring-2 ring-primary/30"
      )}
    >
      {/* Column header */}
      <div className="flex items-center gap-2 px-3 py-2.5">
        <span className={cn("h-2 w-2 rounded-full", COLUMN_ACCENT[status])} />
        <span className="text-sm font-semibold">{label}</span>
        <span className="ml-auto rounded-full bg-muted px-2 py-0.5 text-[10px] font-bold text-muted-foreground">
          {applications.length}
        </span>
      </div>

      {/* Cards */}
      <div className="flex-1 space-y-2 overflow-y-auto px-2 pb-2">
        {applications.length === 0 ? (
          <div className="rounded-lg border border-dashed p-3 text-center text-[11px] text-muted-foreground">
            拖拽卡片到此列
          </div>
        ) : (
          applications.map((app) => (
            <KanbanCard key={app.id} application={app} job={jobsMap[app.job_id]} />
          ))
        )}
      </div>
    </div>
  );
}
