"use client";

import { useState } from "react";
import { FileText, Loader2, Star } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import * as resumesApi from "@/lib/api/resumes";
import { toast } from "@/stores/toast-store";
import type { ResumeResponse } from "@/types/resume";

interface ResumeCardProps {
  resume: ResumeResponse;
  onSelect: (resume: ResumeResponse) => void;
  onActivated: () => void;
  selected: boolean;
}

export function ResumeCard({ resume, onSelect, onActivated, selected }: ResumeCardProps) {
  const [activating, setActivating] = useState(false);

  const setActive = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setActivating(true);
    try {
      await resumesApi.updateResume(resume.id, { is_active: true });
      onActivated();
    } catch (e) {
      console.error("Failed to set active resume:", e);
      toast.error("设置活跃简历失败");
    } finally {
      setActivating(false);
    }
  };

  return (
    <button
      type="button"
      onClick={() => onSelect(resume)}
      className={cn(
        "w-full rounded-xl border border-l-4 border-l-primary bg-card p-4 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md",
        selected && "ring-2 ring-primary"
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2.5">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10">
            <FileText className="h-4 w-4 text-primary" />
          </div>
          <div className="min-w-0">
            <h3 className="truncate text-sm font-semibold">{resume.title}</h3>
            <p className="mt-0.5 truncate text-xs text-muted-foreground">
              {resume.target_direction || "未设置方向"}
            </p>
          </div>
        </div>
        {resume.is_active && (
          <Badge variant="success" className="shrink-0">
            活跃
          </Badge>
        )}
      </div>

      <div className="mt-3 flex items-center justify-between">
        <span className="text-[11px] text-muted-foreground">
          版本 {resume.version}
          {resume.file_type ? ` · ${resume.file_type}` : ""}
        </span>
        {!resume.is_active && (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs"
            onClick={setActive}
            disabled={activating}
          >
            {activating ? (
              <Loader2 className="mr-1 h-3 w-3 animate-spin" />
            ) : (
              <Star className="mr-1 h-3 w-3" />
            )}
            设为活跃
          </Button>
        )}
      </div>
    </button>
  );
}
