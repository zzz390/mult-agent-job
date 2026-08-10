"use client";

import { Briefcase, Calendar, ChevronRight, MapPin } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { JobResponse } from "@/types/job";

interface JobCardProps {
  job: JobResponse;
  onSelect: (job: JobResponse) => void;
}

export function JobCard({ job, onSelect }: JobCardProps) {
  return (
    <button
      type="button"
      onClick={() => onSelect(job)}
      className="group w-full rounded-xl border border-l-4 border-l-primary bg-card p-4 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold group-hover:text-primary">
            {job.title}
          </h3>
          <p className="mt-0.5 truncate text-xs text-muted-foreground">
            {job.company}
            {job.company_type ? ` · ${job.company_type}` : ""}
          </p>
        </div>
        <ChevronRight className="mt-1 h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        {job.salary_range && (
          <span className="font-medium text-primary">{job.salary_range}</span>
        )}
        {job.location && (
          <span className="flex items-center gap-1">
            <MapPin className="h-3 w-3" />
            {job.location}
          </span>
        )}
        {job.deadline && (
          <span className="flex items-center gap-1">
            <Calendar className="h-3 w-3" />
            截止 {job.deadline}
          </span>
        )}
        <span className="flex items-center gap-1">
          <Briefcase className="h-3 w-3" />
          {job.source_platform}
        </span>
      </div>

      {job.skills_required.length > 0 && (
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {job.skills_required.slice(0, 5).map((skill) => (
            <Badge key={skill} variant="secondary" className="px-1.5 py-0 text-[10px]">
              {skill}
            </Badge>
          ))}
          {job.skills_required.length > 5 && (
            <Badge variant="outline" className="px-1.5 py-0 text-[10px]">
              +{job.skills_required.length - 5}
            </Badge>
          )}
        </div>
      )}
    </button>
  );
}
