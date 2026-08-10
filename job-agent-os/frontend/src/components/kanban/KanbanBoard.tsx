"use client";

import { useMemo, useState } from "react";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { KanbanColumn } from "./KanbanColumn";
import { KanbanCard } from "./KanbanCard";
import { toast } from "@/stores/toast-store";
import * as applicationsApi from "@/lib/api/applications";
import {
  KANBAN_COLUMNS,
  type ApplicationResponse,
  type ApplicationStatus,
  type KanbanView,
} from "@/types/application";
import type { JobResponse } from "@/types/job";

interface KanbanBoardProps {
  kanban: KanbanView;
  jobsMap: Record<string, JobResponse>;
  /** Called after a successful status change to refresh the board */
  onChanged: () => void;
}

export function KanbanBoard({ kanban, jobsMap, onChanged }: KanbanBoardProps) {
  const [activeApp, setActiveApp] = useState<ApplicationResponse | null>(null);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } })
  );

  // Index applications by id for quick lookup during drag
  const appsById = useMemo(() => {
    const map: Record<string, ApplicationResponse> = {};
    for (const col of KANBAN_COLUMNS) {
      for (const app of kanban[col.key] ?? []) {
        map[app.id] = app;
      }
    }
    return map;
  }, [kanban]);

  const handleDragStart = (event: DragStartEvent) => {
    const app = appsById[String(event.active.id)];
    setActiveApp(app ?? null);
  };

  const handleDragEnd = async (event: DragEndEvent) => {
    setActiveApp(null);
    const { active, over } = event;
    if (!over) return;

    const appId = String(active.id);
    const targetStatus = String(over.id) as ApplicationStatus;
    const app = appsById[appId];
    if (!app) return;

    // Dropped on the same column -> no-op
    if (app.status === targetStatus) return;

    // Optimistic: the backend validates the transition; on failure show a toast.
    try {
      await applicationsApi.updateApplicationStatus(appId, { status: targetStatus });
      const label = KANBAN_COLUMNS.find((c) => c.key === targetStatus)?.label ?? targetStatus;
      toast.success("状态已更新", `已移动到「${label}」`);
      onChanged();
    } catch (e) {
      toast.error(
        "状态流转失败",
        e instanceof Error ? e.message : "该状态流转不被允许"
      );
    }
  };

  return (
    <DndContext
      sensors={sensors}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
      onDragCancel={() => setActiveApp(null)}
    >
      <div className="flex h-full gap-3 overflow-x-auto p-4 lg:p-6">
        {KANBAN_COLUMNS.map((col) => (
          <KanbanColumn
            key={col.key}
            status={col.key}
            label={col.label}
            applications={kanban[col.key] ?? []}
            jobsMap={jobsMap}
          />
        ))}
      </div>

      <DragOverlay>
        {activeApp ? (
          <div className="w-60">
            <KanbanCard application={activeApp} job={jobsMap[activeApp.job_id]} overlay />
          </div>
        ) : null}
      </DragOverlay>
    </DndContext>
  );
}
