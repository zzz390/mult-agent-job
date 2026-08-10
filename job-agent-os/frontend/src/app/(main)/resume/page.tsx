"use client";

import { useCallback, useEffect, useState } from "react";
import { FileText } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { ResumeUploader } from "@/components/resume/ResumeUploader";
import { ResumeCard } from "@/components/resume/ResumeCard";
import { ResumeDetail } from "@/components/resume/ResumeDetail";
import * as resumesApi from "@/lib/api/resumes";
import { toast } from "@/stores/toast-store";
import type { ResumeResponse } from "@/types/resume";

export default function ResumePage() {
  const [resumes, setResumes] = useState<ResumeResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<ResumeResponse | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await resumesApi.listResumes({ page: 1, page_size: 50 });
      setResumes(data.items);
      // Keep selection in sync (e.g. after activation changes)
      setSelected((prev) =>
        prev ? data.items.find((r) => r.id === prev.id) ?? null : null
      );
    } catch (e) {
      console.error("Failed to load resumes:", e);
      toast.error("加载失败", "简历列表加载失败，请稍后重试");
      setResumes([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Header */}
      <div className="border-b bg-card px-4 py-4 lg:px-6">
        <div className="flex items-center gap-2">
          <FileText className="h-5 w-5 text-primary" />
          <h1 className="text-lg font-bold">简历管理</h1>
          <span className="text-xs text-muted-foreground">
            共 {resumes.length} 份简历
          </span>
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-4 lg:p-6">
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[380px_1fr]">
          {/* Left: uploader + list */}
          <div className="space-y-4">
            <ResumeUploader onUploaded={load} />

            <div className="space-y-3">
              {loading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} className="h-24 rounded-xl" />
                ))
              ) : resumes.length === 0 ? (
                <div className="rounded-xl border border-dashed p-6 text-center">
                  <p className="text-sm text-muted-foreground">
                    还没有简历，上传一份开始吧。
                  </p>
                </div>
              ) : (
                resumes.map((r) => (
                  <ResumeCard
                    key={r.id}
                    resume={r}
                    selected={selected?.id === r.id}
                    onSelect={setSelected}
                    onActivated={load}
                  />
                ))
              )}
            </div>
          </div>

          {/* Right: detail */}
          <div>
            {selected ? (
              <ResumeDetail resume={selected} />
            ) : (
              <div className="flex h-full min-h-[300px] flex-col items-center justify-center gap-3 rounded-xl border border-dashed text-center">
                <FileText className="h-8 w-8 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">
                  选择左侧简历查看结构化详情
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
