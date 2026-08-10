"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, ChevronDown, Circle, Star } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { GeneratedQuestion } from "@/lib/api/interview";

const FAV_KEY = "interview_favorites";
const PRACTICED_KEY = "interview_practiced";

function loadSet(key: string): Set<number> {
  if (typeof window === "undefined") return new Set();
  try {
    const raw = localStorage.getItem(key);
    return raw ? new Set(JSON.parse(raw) as number[]) : new Set();
  } catch {
    return new Set();
  }
}

function saveSet(key: string, set: Set<number>) {
  if (typeof window === "undefined") return;
  localStorage.setItem(key, JSON.stringify(Array.from(set)));
}

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

function QuestionItem({
  q,
  isFavorite,
  isPracticed,
  onToggleFavorite,
  onTogglePracticed,
}: {
  q: GeneratedQuestion;
  isFavorite: boolean;
  isPracticed: boolean;
  onToggleFavorite: (id: number) => void;
  onTogglePracticed: (id: number) => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-lg border bg-card">
      <div className="flex w-full items-start gap-2 p-3">
        <button
          type="button"
          onClick={() => onTogglePracticed(q.id)}
          title={isPracticed ? "已练习" : "标记已练习"}
          className="mt-0.5 shrink-0"
        >
          {isPracticed ? (
            <CheckCircle2 className="h-5 w-5 text-emerald-500" />
          ) : (
            <Circle className="h-5 w-5 text-muted-foreground/40 hover:text-muted-foreground" />
          )}
        </button>

        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex flex-1 items-start gap-2 text-left"
        >
          <span className="flex-1 text-sm font-medium leading-relaxed">{q.question}</span>
          <span className="flex shrink-0 items-center gap-1.5">
            {difficultyBadge(q.difficulty)}
            <ChevronDown
              className={cn("h-4 w-4 text-muted-foreground transition-transform", open && "rotate-180")}
            />
          </span>
        </button>

        <button
          type="button"
          onClick={() => onToggleFavorite(q.id)}
          title={isFavorite ? "取消收藏" : "收藏"}
          className="mt-0.5 shrink-0"
        >
          <Star
            className={cn(
              "h-4 w-4",
              isFavorite ? "fill-amber-400 text-amber-400" : "text-muted-foreground/40 hover:text-amber-400"
            )}
          />
        </button>
      </div>

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
              <ul className="list-inside list-disc space-y-0.5 rounded-md bg-muted p-2 text-xs text-muted-foreground">
                {q.scoring_criteria.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </div>
          )}
          {q.follow_up && (
            <div>
              <div className="mb-1 text-[10px] font-bold uppercase text-primary">追问</div>
              <p className="rounded-md bg-muted p-2 text-xs text-muted-foreground">{q.follow_up}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function QuestionList({ questions }: { questions: GeneratedQuestion[] }) {
  const [favorites, setFavorites] = useState<Set<number>>(new Set());
  const [practiced, setPracticed] = useState<Set<number>>(new Set());

  useEffect(() => {
    setFavorites(loadSet(FAV_KEY));
    setPracticed(loadSet(PRACTICED_KEY));
  }, []);

  const toggleFavorite = (id: number) => {
    setFavorites((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      saveSet(FAV_KEY, next);
      return next;
    });
  };

  const togglePracticed = (id: number) => {
    setPracticed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      saveSet(PRACTICED_KEY, next);
      return next;
    });
  };

  const technical = questions.filter((q) => q.type === "technical");
  const behavioral = questions.filter((q) => q.type === "behavioral");
  const other = questions.filter((q) => q.type !== "technical" && q.type !== "behavioral");

  const renderList = (list: GeneratedQuestion[]) =>
    list.length === 0 ? (
      <p className="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">暂无题目</p>
    ) : (
      <div className="space-y-2">
        {list.map((q) => (
          <QuestionItem
            key={q.id}
            q={q}
            isFavorite={favorites.has(q.id)}
            isPracticed={practiced.has(q.id)}
            onToggleFavorite={toggleFavorite}
            onTogglePracticed={togglePracticed}
          />
        ))}
      </div>
    );

  return (
    <div>
      <div className="mb-3 flex items-center gap-3 text-xs text-muted-foreground">
        <span>共 {questions.length} 道题</span>
        <span className="flex items-center gap-1">
          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
          已练习 {practiced.size}
        </span>
        <span className="flex items-center gap-1">
          <Star className="h-3.5 w-3.5 fill-amber-400 text-amber-400" />
          收藏 {favorites.size}
        </span>
      </div>

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
    </div>
  );
}
