"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ArrowLeft, History } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { ChatStream } from "@/components/chat/ChatStream";
import { SessionList } from "@/components/chat/SessionList";
import type { ChatMessage } from "@/stores/chat-store";
import * as sessionsApi from "@/lib/api/sessions";
import type {
  SessionResponse,
  SessionProgress,
  TimelineEvent,
} from "@/types/session";
import { PIPELINE_STEPS } from "@/components/chat/ProgressCard";

let idCounter = 0;
function nextId() {
  idCounter += 1;
  return `hist-${idCounter}`;
}

/** Reconstruct read-only chat messages from session + timeline data. */
function buildMessages(
  session: SessionResponse,
  timeline: TimelineEvent[]
): ChatMessage[] {
  const msgs: ChatMessage[] = [];
  const completed: string[] = [];

  if (session.intent) {
    msgs.push({
      id: nextId(),
      kind: "user",
      content: session.intent,
      timestamp: 0,
      readOnly: true,
    });
    msgs.push({
      id: nextId(),
      kind: "system",
      content: "已收到你的求职意向，Agent 团队开始协作处理...",
      timestamp: 0,
      readOnly: true,
    });
  }

  for (const ev of timeline) {
    if (ev.event.startsWith("step_completed:")) {
      const step = ev.event.split(":")[1];
      completed.push(step);
      const progress: SessionProgress = {
        completed_steps: [...completed],
        current_step: null,
        pending_steps: PIPELINE_STEPS.map((s) => s.key).filter(
          (k) => !completed.includes(k)
        ),
      };
      msgs.push({
        id: nextId(),
        kind: "progress",
        content: "Agent 执行进度",
        timestamp: 0,
        progress,
        readOnly: true,
      });
    } else if (ev.event === "session_completed") {
      msgs.push({
        id: nextId(),
        kind: "result",
        content: "流程已完成",
        timestamp: 0,
        resultsSummary: ev.data,
        readOnly: true,
      });
    } else if (ev.event === "session_error") {
      msgs.push({
        id: nextId(),
        kind: "error",
        content:
          typeof ev.data?.error === "string" ? ev.data.error : "执行失败",
        timestamp: 0,
        readOnly: true,
      });
    }
  }

  // If no timeline step events but session has progress, show a final progress card
  if (completed.length === 0 && session.progress) {
    msgs.push({
      id: nextId(),
      kind: "progress",
      content: "Agent 执行进度",
      timestamp: 0,
      progress: session.progress,
      readOnly: true,
    });
  }

  return msgs;
}

export default function SessionHistoryPage() {
  const params = useParams<{ sessionId: string }>();
  const sessionId = params.sessionId;

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [session, setSession] = useState<SessionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    let mounted = true;
    async function load() {
      setLoading(true);
      setNotFound(false);
      try {
        const [sess, timeline] = await Promise.all([
          sessionsApi.getSession(sessionId),
          sessionsApi.getSessionTimeline(sessionId).catch(() => [] as TimelineEvent[]),
        ]);
        if (!mounted) return;
        setSession(sess);

        let msgs = buildMessages(sess, timeline);

        // Enrich with recommendations if available (read-only)
        try {
          const recs = await sessionsApi.getRecommendations(sessionId);
          if (recs && recs.length > 0) {
            msgs = [
              ...msgs,
              {
                id: nextId(),
                kind: "recommendation",
                content: "岗位推荐结果",
                timestamp: 0,
                recommendations: recs,
                readOnly: true,
                resolved: true,
              },
            ];
          }
        } catch {
          // recommendations not available; ignore
        }

        setMessages(msgs);
      } catch {
        if (mounted) setNotFound(true);
      } finally {
        if (mounted) setLoading(false);
      }
    }
    if (sessionId) load();
    return () => {
      mounted = false;
    };
  }, [sessionId]);

  return (
    <div className="flex h-full">
      {/* Left session list */}
      <SessionList />

      {/* Main column */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* History header */}
        <div className="flex items-center gap-3 border-b bg-card px-4 py-3">
          <Button asChild variant="ghost" size="sm">
            <Link href="/chat">
              <ArrowLeft className="mr-1 h-4 w-4" />
              返回
            </Link>
          </Button>
          <div className="flex items-center gap-2">
            <History className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-semibold">
              {session?.intent || "历史会话"}
            </span>
          </div>
          {session && (
            <Badge
              variant={
                session.status === "completed"
                  ? "success"
                  : session.status === "failed"
                    ? "destructive"
                    : "secondary"
              }
              className="ml-auto"
            >
              {session.status}
            </Badge>
          )}
        </div>

        {/* Body */}
        {loading ? (
          <div className="flex-1 space-y-4 overflow-hidden p-6">
            <Skeleton className="ml-auto h-10 w-1/3 rounded-2xl" />
            <Skeleton className="h-10 w-1/2 rounded-2xl" />
            <Skeleton className="h-24 w-full rounded-xl" />
            <Skeleton className="h-24 w-full rounded-xl" />
          </div>
        ) : notFound ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
            <p className="text-sm text-muted-foreground">
              未找到该会话，可能已被清理。
            </p>
            <Button asChild variant="outline" size="sm">
              <Link href="/chat">返回对话</Link>
            </Button>
          </div>
        ) : (
          <ChatStream messages={messages} />
        )}
      </div>
    </div>
  );
}
