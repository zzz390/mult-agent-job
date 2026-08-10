"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Briefcase, ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { JobFilters } from "@/components/jobs/JobFilters";
import { JobCard } from "@/components/jobs/JobCard";
import { JobDetailDrawer } from "@/components/jobs/JobDetailDrawer";
import { ManualJobDialog } from "@/components/jobs/ManualJobDialog";
import * as jobsApi from "@/lib/api/jobs";
import { toast } from "@/stores/toast-store";
import type { JobFilters as JobFiltersType, JobResponse } from "@/types/job";
import type { PaginationMeta } from "@/types/api";

const PAGE_SIZE = 12;

export default function JobsPage() {
  const [filters, setFilters] = useState<JobFiltersType>({});
  const [debouncedFilters, setDebouncedFilters] = useState<JobFiltersType>({});
  const [page, setPage] = useState(1);
  const [jobs, setJobs] = useState<JobResponse[]>([]);
  const [pagination, setPagination] = useState<PaginationMeta | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const debounceRef = useRef<NodeJS.Timeout | null>(null);

  // Debounce filter changes -> reset to page 1
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setDebouncedFilters(filters);
      setPage(1);
    }, 400);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [filters]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await jobsApi.listJobs({
        ...debouncedFilters,
        page,
        page_size: PAGE_SIZE,
      });
      setJobs(data.items);
      setPagination(data.pagination);
    } catch (e) {
      console.error("Failed to load jobs:", e);
      toast.error("加载失败", "岗位列表加载失败，请稍后重试");
      setJobs([]);
      setPagination(null);
    } finally {
      setLoading(false);
    }
  }, [debouncedFilters, page]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Header */}
      <div className="border-b bg-card px-4 py-4 lg:px-6">
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Briefcase className="h-5 w-5 text-primary" />
            <h1 className="text-lg font-bold">岗位列表</h1>
            {pagination && (
              <span className="text-xs text-muted-foreground">
                共 {pagination.total_items} 个岗位
              </span>
            )}
          </div>
          <ManualJobDialog onCreated={load} />
        </div>
        <JobFilters filters={filters} onChange={setFilters} />
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-4 lg:p-6">
        {loading ? (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-36 rounded-xl" />
            ))}
          </div>
        ) : jobs.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-muted">
              <Briefcase className="h-7 w-7 text-muted-foreground" />
            </div>
            <p className="text-sm text-muted-foreground">
              暂无匹配的岗位，试试调整筛选条件或通过对话搜索岗位。
            </p>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
              {jobs.map((job) => (
                <JobCard key={job.id} job={job} onSelect={(j) => setSelectedJobId(j.id)} />
              ))}
            </div>

            {/* Pagination */}
            {pagination && pagination.total_pages > 1 && (
              <div className="mt-6 flex items-center justify-center gap-3">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!pagination.has_prev}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  <ChevronLeft className="mr-1 h-4 w-4" />
                  上一页
                </Button>
                <span className="text-sm text-muted-foreground">
                  {pagination.page} / {pagination.total_pages}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!pagination.has_next}
                  onClick={() => setPage((p) => p + 1)}
                >
                  下一页
                  <ChevronRight className="ml-1 h-4 w-4" />
                </Button>
              </div>
            )}
          </>
        )}
      </div>

      {/* Detail drawer */}
      <JobDetailDrawer jobId={selectedJobId} onClose={() => setSelectedJobId(null)} />
    </div>
  );
}

