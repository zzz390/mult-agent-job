"use client";

import { useCallback, useEffect, useState } from "react";
import { KanbanSquare, TrendingUp } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { KanbanBoard } from "@/components/kanban/KanbanBoard";
import * as applicationsApi from "@/lib/api/applications";
import * as jobsApi from "@/lib/api/jobs";
import { toast } from "@/stores/toast-store";
import type {
  ApplicationStatistics,
  KanbanView,
} from "@/types/application";
import type { JobResponse } from "@/types/job";

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex flex-col rounded-xl border bg-card px-4 py-3 shadow-sm">
      <span className="text-lg font-bold text-primary">{value}</span>
      <span className="text-[11px] text-muted-foreground">{label}</span>
    </div>
  );
}

export default function KanbanPage() {
  const [kanban, setKanban] = useState<KanbanView | null>(null);
  const [stats, setStats] = useState<ApplicationStatistics | null>(null);
  const [jobsMap, setJobsMap] = useState<Record<string, JobResponse>>({});
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [kb, st] = await Promise.all([
        applicationsApi.getKanban(),
        applicationsApi.getStatistics().catch(() => null),
      ]);
      setKanban(kb);
      setStats(st);

      // Collect unique job ids and fetch their details for card display
      const jobIds = new Set<string>();
      const allApps = [
        ...kb.pending,
        ...kb.applied,
        ...kb.written_test,
        ...kb.round1,
        ...kb.round2,
        ...kb.hr_interview,
        ...kb.offer,
        ...kb.rejected,
      ];
      allApps.forEach((a) => jobIds.add(a.job_id));

      const results = await Promise.allSettled(
        Array.from(jobIds).map((id) => jobsApi.getJob(id))
      );
      const map: Record<string, JobResponse> = {};
      results.forEach((r, i) => {
        if (r.status === "fulfilled") {
          map[Array.from(jobIds)[i]] = r.value;
        }
      });
      setJobsMap(map);
    } catch (e) {
      console.error("Failed to load kanban:", e);
      toast.error("加载失败", "看板数据加载失败，请稍后重试");
      setKanban(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Header + statistics */}
      <div className="border-b bg-card px-4 py-4 lg:px-6">
        <div className="mb-3 flex items-center gap-2">
          <KanbanSquare className="h-5 w-5 text-primary" />
          <h1 className="text-lg font-bold">投递看板</h1>
          <span className="flex items-center gap-1 text-xs text-muted-foreground">
            <TrendingUp className="h-3.5 w-3.5" />
            拖拽卡片更新投递状态
          </span>
        </div>

        {loading ? (
          <div className="flex gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-32 rounded-xl" />
            ))}
          </div>
        ) : (
          <div className="flex flex-wrap gap-3">
            <StatCard label="总投递" value={stats?.total_applications ?? kanban?.statistics?.total ?? 0} />
            <StatCard label="进行中" value={kanban?.statistics?.in_progress ?? 0} />
            <StatCard label="Offer" value={kanban?.statistics?.offer_count ?? 0} />
            <StatCard
              label="平均匹配分"
              value={stats?.avg_match_score ? Math.round(stats.avg_match_score) : "-"}
            />
            <StatCard
              label="通过率"
              value={stats?.pass_rate !== undefined ? `${stats.pass_rate}%` : "-"}
            />
          </div>
        )}
      </div>

      {/* Board */}
      <div className="flex-1 overflow-hidden">
        {loading ? (
          <div className="flex gap-3 overflow-hidden p-6">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-96 w-64 shrink-0 rounded-xl" />
            ))}
          </div>
        ) : kanban ? (
          <KanbanBoard kanban={kanban} jobsMap={jobsMap} onChanged={load} />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
            <KanbanSquare className="h-8 w-8 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              暂无投递记录，通过对话流程创建投递后即可在此管理。
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

