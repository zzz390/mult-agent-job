"use client";

import { AlertTriangle, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { ChatMessage } from "@/stores/chat-store";

interface ErrorCardProps {
  message: ChatMessage;
  /** Optional retry handler (e.g. reset and allow a new session) */
  onRetry?: () => void;
}

export function ErrorCard({ message, onRetry }: ErrorCardProps) {
  return (
    <div className="w-full rounded-xl border border-l-4 border-l-destructive bg-card p-4 shadow-sm">
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 text-destructive" />
        <span className="text-sm font-semibold">{message.content}</span>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        执行过程中出现问题，你可以重试或重新发起新的会话。
      </p>
      {onRetry && !message.readOnly && (
        <Button variant="outline" size="sm" className="mt-3" onClick={onRetry}>
          <RotateCcw className="mr-2 h-3.5 w-3.5" />
          重试
        </Button>
      )}
    </div>
  );
}
