"use client";

import { useDraggable } from "@dnd-kit/core";
import { GripVertical } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import type { ApplicationResponse } from "@/types/application";
import type { JobResponse } from "@/types/job";

const PRIORITY_BAR: Record<string, string> = {
  high: "bg-destructive",
  medium: "bg-amber-500",
  low: "bg-emerald-500",
};

interface KanbanCardProps {
  application: ApplicationResponse;
  job?: JobResponse;
  /** When rendered inside DragOverlay (no drag handlers needed) */
  overlay?: boolean;
}

export function KanbanCard({ application, job, overlay }: KanbanCardProps) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: application.id,
    disabled: overlay,
  });

  return (
    <div
      ref={overlay ? undefined : setNodeRef}
      {...(overlay ? {} : attributes)}
      {...(overlay ? {} : listeners)}
      className={cn(
        "group relative cursor-grab overflow-hidden rounded-lg border bg-card p-3 shadow-sm transition-shadow hover:shadow-md active:cursor-grabbing",
        isDragging && "opacity-40",
        overlay && "rotate-2 shadow-xl ring-2 ring-primary"
      )}
    >
      {/* Priority color bar */}
      <span
        className={cn(
          "absolute inset-y-0 left-0 w-1",
          PRIORITY_BAR[application.priority] ?? "bg-muted-foreground"
        )}
      />

      <div className="pl-2">
        <div className="flex items-start justify-between gap-1">
          <p className="line-clamp-1 text-sm font-semibold">
            {job?.title ?? "加载中..."}
          </p>
          <GripVertical className="h-4 w-4 shrink-0 text-muted-foreground/40" />
        </div>
        <p className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">
          {job?.company ?? application.job_id.slice(0, 8)}
        </p>

        <div className="mt-2 flex items-center justify-between gap-2">
          {application.match_score !== null && application.match_score !== undefined ? (
            <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">
              匹配 {Math.round(application.match_score)}
            </Badge>
          ) : (
            <span />
          )}
          {job?.location && (
            <span className="truncate text-[10px] text-muted-foreground">
              {job.location}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
