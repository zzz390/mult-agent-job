"use client";

import { Bot, User } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/stores/chat-store";
import { ProgressCard } from "./ProgressCard";
import { ClarificationCard } from "./ClarificationCard";
import { ApprovalCard } from "./ApprovalCard";
import { RecommendationCard } from "./RecommendationCard";
import { ResumeDiffCard } from "./ResumeDiffCard";
import { InterviewCard } from "./InterviewCard";
import { ResultSummaryCard } from "./ResultSummaryCard";
import { ErrorCard } from "./ErrorCard";

export function MessageBubble({
  message,
  onRetry,
}: {
  message: ChatMessage;
  onRetry?: () => void;
}) {
  // Rich cards render full-width
  if (message.kind === "progress" && message.progress) {
    return <ProgressCard progress={message.progress} />;
  }
  if (message.kind === "clarification") {
    return (
      <ClarificationCard
        message={message}
      />
    );
  }
  if (message.kind === "approval" && message.approval) {
    return <ApprovalCard message={message} />;
  }
  if (message.kind === "recommendation") {
    return <RecommendationCard message={message} />;
  }
  if (message.kind === "resume_diff") {
    return <ResumeDiffCard message={message} />;
  }
  if (message.kind === "interview") {
    return <InterviewCard message={message} />;
  }
  if (message.kind === "result") {
    return <ResultSummaryCard message={message} />;
  }
  if (message.kind === "error") {
    return <ErrorCard message={message} onRetry={onRetry} />;
  }

  const isUser = message.kind === "user";

  return (
    <div className={cn("flex gap-3", isUser ? "justify-end" : "justify-start")}>
      {!isUser && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary">
          <Bot className="h-4 w-4 text-primary-foreground" />
        </div>
      )}
      <div
        className={cn(
          "max-w-[75%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
          isUser
            ? "rounded-br-sm bg-primary text-primary-foreground"
            : "rounded-bl-sm bg-muted text-foreground"
        )}
      >
        {message.content}
      </div>
      {isUser && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-secondary">
          <User className="h-4 w-4 text-secondary-foreground" />
        </div>
      )}
    </div>
  );
}
