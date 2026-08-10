"use client";

import { useState } from "react";
import { ChevronDown, GraduationCap } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { ChatMessage } from "@/stores/chat-store";
import type { InterviewQuestion } from "@/types/session";

function difficultyBadge(difficulty: string) {
  switch (difficulty) {
    case "easy":
      return <Badge variant="success">简单</Badge>;
    case "medium":
      return <Badge variant="warning">中等</Badge>;
    case "hard":
      return <Badge variant="destructive">困难</Badge>;
    default:
      return <Badge variant="secondary">{difficulty}</Badge>;
  }
}

function QuestionItem({ q, index }: { q: InterviewQuestion; index: number }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-lg border">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start gap-2 p-3 text-left"
      >
        <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[10px] font-bold text-primary">
          {index + 1}
        </span>
        <span className="flex-1 text-sm font-medium leading-relaxed">{q.question}</span>
        <span className="flex shrink-0 items-center gap-1.5">
          {difficultyBadge(q.difficulty)}
          <ChevronDown
            className={cn("h-4 w-4 text-muted-foreground transition-transform", open && "rotate-180")}
          />
        </span>
      </button>

      {open && (
        <div className="space-y-2 border-t px-3 pb-3 pt-2">
          {q.reference_answer && (
            <div>
              <div className="mb-1 text-[10px] font-bold uppercase text-primary">参考答案</div>
              <p className="whitespace-pre-wrap rounded-md bg-muted p-2 text-xs leading-relaxed text-muted-foreground">
                {q.reference_answer}
              </p>
            </div>
          )}
          {q.scoring_criteria && q.scoring_criteria.length > 0 && (
            <div>
              <div className="mb-1 text-[10px] font-bold uppercase text-primary">评分标准</div>
              <ul className="list-inside list-disc space-y-0.5 rounded-md bg-muted p-2 text-xs leading-relaxed text-muted-foreground">
                {q.scoring_criteria.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </div>
          )}
          {q.follow_up && (
            <div>
              <div className="mb-1 text-[10px] font-bold uppercase text-primary">追问</div>
              <p className="whitespace-pre-wrap rounded-md bg-muted p-2 text-xs leading-relaxed text-muted-foreground">
                {q.follow_up}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function InterviewCard({ message }: { message: ChatMessage }) {
  const questions = message.questions ?? [];
  const technical = questions.filter((q) => q.type === "technical");
  const behavioral = questions.filter((q) => q.type === "behavioral");
  const other = questions.filter((q) => q.type !== "technical" && q.type !== "behavioral");

  const renderList = (list: InterviewQuestion[]) =>
    list.length === 0 ? (
      <p className="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">暂无题目</p>
    ) : (
      <div className="space-y-2">
        {list.map((q, i) => (
          <QuestionItem key={i} q={q} index={i} />
        ))}
      </div>
    );

  return (
    <div className="w-full rounded-xl border border-l-4 border-l-sky-500 bg-card p-4 shadow-sm">
      <div className="mb-2 flex items-center gap-2">
        <GraduationCap className="h-4 w-4 text-sky-500" />
        <span className="text-sm font-semibold">面试题已生成</span>
        <Badge variant="secondary" className="ml-auto">
          {questions.length} 道题
        </Badge>
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        点击题目可展开查看参考答案与评分标准。
      </p>

      {questions.length === 0 ? (
        <p className="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
          暂无面试题数据。
        </p>
      ) : (
        <Tabs defaultValue="technical">
          <TabsList className="w-full">
            <TabsTrigger value="technical" className="flex-1">
              技术题 ({technical.length})
            </TabsTrigger>
            <TabsTrigger value="behavioral" className="flex-1">
              行为题 ({behavioral.length})
            </TabsTrigger>
            {other.length > 0 && (
              <TabsTrigger value="other" className="flex-1">
                其他 ({other.length})
              </TabsTrigger>
            )}
          </TabsList>
          <TabsContent value="technical">{renderList(technical)}</TabsContent>
          <TabsContent value="behavioral">{renderList(behavioral)}</TabsContent>
          {other.length > 0 && <TabsContent value="other">{renderList(other)}</TabsContent>}
        </Tabs>
      )}
    </div>
  );
}
