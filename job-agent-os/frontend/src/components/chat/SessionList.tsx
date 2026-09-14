"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Loader2, Menu, MessageSquare, Plus, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import * as sessionsApi from "@/lib/api/sessions";
import { useChatStore } from "@/stores/chat-store";
import { useSessionStore } from "@/stores/session-store";
import { resetSessionPolling } from "@/lib/hooks/useSession";
import { toast } from "@/stores/toast-store";
import type { SessionResponse, SessionStatus } from "@/types/session";

function statusBadge(status: SessionStatus) {
  switch (status) {
    case "completed":
      return <Badge variant="success">完成</Badge>;
    case "failed":
      return <Badge variant="destructive">失败</Badge>;
    case "cancelled":
      return <Badge variant="secondary">已取消</Badge>;
    case "waiting_approval":
      return <Badge variant="warning">待审批</Badge>;
    case "running":
      return <Badge variant="default">进行中</Badge>;
    default:
      return <Badge variant="outline">{status}</Badge>;
  }
}

function formatTime(iso: string | null) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Shared session list content (used by desktop sidebar + mobile drawer). */
export function SessionListContent({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const router = useRouter();
  const [sessions, setSessions] = useState<SessionResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const activeSessionId = useSessionStore((s) => s.sessionId);
  const chatSessionId = useChatStore((s) => s.sessionId);
  const clearChat = useChatStore((s) => s.clear);
  const resetSession = useSessionStore((s) => s.reset);
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    sessionsApi
      .listSessions()
      .then((data) => {
        if (mounted) setSessions(data);
      })
      .catch(() => undefined)
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [pathname, activeSessionId]);

  const startNew = () => {
    resetSessionPolling();
    clearChat();
    resetSession();
    onNavigate?.();
    router.push("/chat");
  };

  const deleteSession = async (session: SessionResponse) => {
    const confirmed = window.confirm(
      `删除“${session.intent || "求职会话"}”？删除后无法恢复。`
    );
    if (!confirmed) return;

    setDeletingSessionId(session.session_id);
    try {
      await sessionsApi.deleteSession(session.session_id);
      setSessions((items) => items.filter((item) => item.session_id !== session.session_id));

      const isOpenSession =
        session.session_id === activeSessionId ||
        session.session_id === chatSessionId ||
        pathname === `/chat/${session.session_id}`;
      if (isOpenSession) {
        resetSessionPolling();
        clearChat();
        resetSession();
        onNavigate?.();
        router.replace("/chat");
      }
      toast.success("会话已删除");
    } catch (error) {
      toast.error(
        "删除会话失败",
        error instanceof Error ? error.message : "请稍后重试"
      );
    } finally {
      setDeletingSessionId(null);
    }
  };

  return (
    <div className="flex h-full flex-col">
      {/* New session */}
      <div className="border-b p-3">
        <Button onClick={startNew} className="w-full" size="sm">
          <Plus className="mr-2 h-4 w-4" />
          新建会话
        </Button>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto p-2">
        {loading ? (
          <div className="space-y-2 p-1">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full rounded-lg" />
            ))}
          </div>
        ) : sessions.length === 0 ? (
          <div className="flex flex-col items-center gap-2 p-6 text-center">
            <MessageSquare className="h-6 w-6 text-muted-foreground" />
            <p className="text-xs text-muted-foreground">暂无会话记录</p>
          </div>
        ) : (
          <div className="space-y-1">
            {sessions.map((s) => {
              const isActive = s.session_id === activeSessionId && pathname === "/chat";
              const isCurrent = pathname === `/chat/${s.session_id}`;
              const isDeleting = deletingSessionId === s.session_id;
              return (
                <div
                  key={s.session_id}
                  className={cn(
                    "group relative rounded-lg border border-transparent transition-colors hover:bg-accent",
                    (isActive || isCurrent) && "border-primary/30 bg-accent"
                  )}
                >
                  <Link
                    href={isActive ? "/chat" : `/chat/${s.session_id}`}
                    onClick={() => onNavigate?.()}
                    className="block px-3 py-2.5 pr-10"
                  >
                    <p className="truncate text-sm font-medium">{s.intent || "求职会话"}</p>
                    <div className="mt-1.5 flex items-center justify-between gap-2">
                      {statusBadge(s.status)}
                      <span className="text-[10px] text-muted-foreground">
                        {formatTime(s.started_at)}
                      </span>
                    </div>
                  </Link>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="absolute right-1 top-1/2 h-8 w-8 -translate-y-1/2 text-muted-foreground opacity-100 hover:bg-destructive/10 hover:text-destructive md:opacity-0 md:group-hover:opacity-100"
                    onClick={() => void deleteSession(s)}
                    disabled={isDeleting}
                    title="删除会话"
                    aria-label={`删除会话：${s.intent || "求职会话"}`}
                  >
                    {isDeleting ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Trash2 className="h-4 w-4" />
                    )}
                  </Button>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

/** Desktop sidebar (hidden on mobile). */
export function SessionList() {
  return (
    <aside className="hidden w-64 shrink-0 flex-col border-r bg-card md:flex">
      <SessionListContent />
    </aside>
  );
}

/** Mobile drawer triggered by a hamburger button. */
export function MobileSessionDrawer() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button
        variant="ghost"
        size="icon"
        className="md:hidden"
        onClick={() => setOpen(true)}
        title="会话列表"
      >
        <Menu className="h-5 w-5" />
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent drawer className="w-full max-w-xs p-0">
          <DialogHeader className="border-b px-4 py-3">
            <DialogTitle className="text-base">会话列表</DialogTitle>
          </DialogHeader>
          <div className="h-[calc(100%-57px)]">
            <SessionListContent onNavigate={() => setOpen(false)} />
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
