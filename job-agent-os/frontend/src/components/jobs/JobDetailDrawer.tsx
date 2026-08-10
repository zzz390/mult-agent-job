"use client";

import { useEffect, useState } from "react";
import { ExternalLink, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import * as jobsApi from "@/lib/api/jobs";
import type { JobResponse } from "@/types/job";

interface JobDetailDrawerProps {
  jobId: string | null;
  onClose: () => void;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="mb-1.5 text-xs font-bold uppercase text-muted-foreground">{title}</h4>
      {children}
    </div>
  );
}

export function JobDetailDrawer({ jobId, onClose }: JobDetailDrawerProps) {
  const [job, setJob] = useState<JobResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!jobId) {
      setJob(null);
      return;
    }
    let mounted = true;
    setLoading(true);
    jobsApi
      .getJob(jobId)
      .then((data) => {
        if (mounted) setJob(data);
      })
      .catch(() => undefined)
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [jobId]);

  const jd = job?.structured_jd ?? {};
  const responsibilities = Array.isArray(jd.responsibilities)
    ? (jd.responsibilities as string[])
    : [];
  const requirements = Array.isArray(jd.requirements)
    ? (jd.requirements as string[])
    : [];

  return (
    <Dialog open={jobId !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent drawer className="flex flex-col">
        {loading ? (
          <div className="flex flex-1 items-center justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
          </div>
        ) : job ? (
          <>
            <DialogHeader>
              <DialogTitle>{job.title}</DialogTitle>
              <DialogDescription>
                {job.company}
                {job.company_type ? ` · ${job.company_type}` : ""}
              </DialogDescription>
            </DialogHeader>

            <div className="flex-1 space-y-5 overflow-y-auto pr-1">
              {/* Meta */}
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
                {job.salary_range && (
                  <span className="font-semibold text-primary">{job.salary_range}</span>
                )}
                {job.location && <span>📍 {job.location}</span>}
                {job.education_required && <span>🎓 {job.education_required}</span>}
                {job.deadline && <span>⏰ 截止 {job.deadline}</span>}
              </div>

              {/* Skills */}
              {job.skills_required.length > 0 && (
                <Section title="技能要求">
                  <div className="flex flex-wrap gap-1.5">
                    {job.skills_required.map((s) => (
                      <Badge key={s} variant="secondary">
                        {s}
                      </Badge>
                    ))}
                  </div>
                </Section>
              )}

              {/* Responsibilities */}
              {responsibilities.length > 0 && (
                <Section title="岗位职责">
                  <ul className="list-inside list-disc space-y-1 text-sm text-muted-foreground">
                    {responsibilities.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                </Section>
              )}

              {/* Requirements */}
              {requirements.length > 0 && (
                <Section title="任职要求">
                  <ul className="list-inside list-disc space-y-1 text-sm text-muted-foreground">
                    {requirements.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                </Section>
              )}

              {/* Raw structured JD */}
              {Object.keys(jd).length > 0 && (
                <Section title="结构化 JD">
                  <pre className="max-h-48 overflow-auto rounded-md bg-muted p-3 text-[11px] leading-relaxed text-muted-foreground">
                    {JSON.stringify(jd, null, 2)}
                  </pre>
                </Section>
              )}
            </div>

            {/* Source link */}
            {job.source_url && (
              <div className="border-t pt-4">
                <Button asChild variant="outline" className="w-full">
                  <a href={job.source_url} target="_blank" rel="noopener noreferrer">
                    <ExternalLink className="mr-2 h-4 w-4" />
                    查看原始链接（{job.source_platform}）
                  </a>
                </Button>
              </div>
            )}
          </>
        ) : (
          <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
            暂无详情
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
