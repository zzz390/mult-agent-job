"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/stores/toast-store";
import * as interviewApi from "@/lib/api/interview";
import type { GeneratedQuestion } from "@/lib/api/interview";
import * as jobsApi from "@/lib/api/jobs";
import type { JobResponse } from "@/types/job";

const POLL_INTERVAL = 1500;
const MAX_POLL_ATTEMPTS = 40;

interface QuestionGeneratorProps {
  onGenerated: (questions: GeneratedQuestion[], jobTitle: string | null) => void;
}

export function QuestionGenerator({ onGenerated }: QuestionGeneratorProps) {
  const [jobs, setJobs] = useState<JobResponse[]>([]);
  const [jobSearch, setJobSearch] = useState("");
  const [selectedJob, setSelectedJob] = useState<JobResponse | null>(null);
  const [questionTypes, setQuestionTypes] = useState<string[]>(["technical", "behavioral"]);
  const [difficulty, setDifficulty] = useState<"easy" | "medium" | "hard" | "mixed">("mixed");
  const [count, setCount] = useState(10);
  const [generating, setGenerating] = useState(false);
  const pollRef = useRef<NodeJS.Timeout | null>(null);
  /** Guards against the terminal branch running more than once (slow responses). */
  const doneRef = useRef(false);
  /** Guards against setState after unmount. */
  const mountedRef = useRef(true);

  // Load jobs for the selector
  useEffect(() => {
    let mounted = true;
    jobsApi
      .listJobs({ page: 1, page_size: 50 })
      .then((data) => {
        if (mounted) setJobs(data.items);
      })
      .catch(() => undefined);
    return () => {
      mounted = false;
    };
  }, []);

  // Cleanup polling on unmount
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const filteredJobs = jobs.filter(
    (j) =>
      j.title.toLowerCase().includes(jobSearch.toLowerCase()) ||
      j.company.toLowerCase().includes(jobSearch.toLowerCase())
  );

  const toggleType = (type: string) => {
    setQuestionTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]
    );
  };

  const generate = async () => {
    if (!selectedJob) {
      toast.error("请先选择岗位");
      return;
    }
    if (questionTypes.length === 0) {
      toast.error("请至少选择一种题目类型");
      return;
    }
    setGenerating(true);
    try {
      const { task_id } = await interviewApi.generateQuestions({
        job_id: selectedJob.id,
        question_types: questionTypes,
        difficulty,
        count,
      });

      // Clear any previous interval and reset the settle guard
      if (pollRef.current) clearInterval(pollRef.current);
      doneRef.current = false;

      // Poll for result
      let attempts = 0;
      pollRef.current = setInterval(async () => {
        if (doneRef.current) return;
        attempts += 1;
        try {
          const result = await interviewApi.getGenerationResult(task_id);
          if (doneRef.current || !mountedRef.current) return;
          if (result.status === "completed" && result.result) {
            doneRef.current = true;
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            setGenerating(false);
            onGenerated(result.result.questions, result.result.job_title);
            toast.success("面试题已生成", `共 ${result.result.questions.length} 道题`);
          } else if (result.status === "failed" || attempts > MAX_POLL_ATTEMPTS) {
            doneRef.current = true;
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            setGenerating(false);
            toast.error("生成失败", "请稍后重试");
          }
        } catch {
          // keep polling
        }
      }, POLL_INTERVAL);
    } catch (e) {
      setGenerating(false);
      toast.error("生成失败", e instanceof Error ? e.message : "请稍后重试");
    }
  };

  return (
    <div className="rounded-xl border bg-card p-4 shadow-sm">
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
        <Sparkles className="h-4 w-4 text-primary" />
        生成面试题
      </div>

      {/* Job selector */}
      <div className="space-y-1.5">
        <Label>选择岗位 *</Label>
        {selectedJob ? (
          <div className="flex items-center justify-between rounded-md border bg-muted/40 px-3 py-2">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{selectedJob.title}</p>
              <p className="truncate text-xs text-muted-foreground">{selectedJob.company}</p>
            </div>
            <Button variant="ghost" size="sm" onClick={() => setSelectedJob(null)}>
              更换
            </Button>
          </div>
        ) : (
          <>
            <Input
              value={jobSearch}
              onChange={(e) => setJobSearch(e.target.value)}
              placeholder="搜索岗位 / 公司..."
            />
            <div className="max-h-36 space-y-1 overflow-y-auto rounded-md border p-1">
              {filteredJobs.length === 0 ? (
                <p className="p-2 text-xs text-muted-foreground">无匹配岗位</p>
              ) : (
                filteredJobs.map((j) => (
                  <button
                    key={j.id}
                    type="button"
                    onClick={() => setSelectedJob(j)}
                    className="block w-full rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent"
                  >
                    <span className="font-medium">{j.title}</span>
                    <span className="ml-2 text-xs text-muted-foreground">{j.company}</span>
                  </button>
                ))
              )}
            </div>
          </>
        )}
      </div>

      {/* Question types */}
      <div className="mt-3 space-y-1.5">
        <Label>题目类型</Label>
        <div className="flex gap-2">
          {[
            { key: "technical", label: "技术题" },
            { key: "behavioral", label: "行为题" },
          ].map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => toggleType(t.key)}
              className={
                questionTypes.includes(t.key)
                  ? "rounded-full bg-primary px-3 py-1 text-xs font-medium text-primary-foreground"
                  : "rounded-full border px-3 py-1 text-xs text-muted-foreground hover:border-primary"
              }
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Difficulty + count */}
      <div className="mt-3 grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label>难度</Label>
          <select
            value={difficulty}
            onChange={(e) => setDifficulty(e.target.value as typeof difficulty)}
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="mixed">混合</option>
            <option value="easy">简单</option>
            <option value="medium">中等</option>
            <option value="hard">困难</option>
          </select>
        </div>
        <div className="space-y-1.5">
          <Label>数量</Label>
          <Input
            type="number"
            min={1}
            max={50}
            value={count}
            onChange={(e) => setCount(Math.max(1, Math.min(50, Number(e.target.value) || 1)))}
          />
        </div>
      </div>

      <Button onClick={generate} disabled={generating} className="mt-4 w-full">
        {generating ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            生成中...
          </>
        ) : (
          <>
            <Sparkles className="mr-2 h-4 w-4" />
            开始生成
          </>
        )}
      </Button>
    </div>
  );
}
