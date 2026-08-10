"use client";

import { useEffect, useRef } from "react";
import { Bot } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useChatStore, type ChatMessage } from "@/stores/chat-store";
import { MessageBubble } from "./MessageBubble";

export function ChatStream({
  onRetry,
  messages: overrideMessages,
}: {
  onRetry?: () => void;
  /** Optional override (used by history view to render read-only messages) */
  messages?: ChatMessage[];
}) {
  const storeMessages = useChatStore((s) => s.messages);
  const messages = overrideMessages ?? storeMessages;
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8 text-center">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10">
          <Bot className="h-8 w-8 text-primary" />
        </div>
        <div>
          <h2 className="text-lg font-semibold">你好，我是你的智能求职助手</h2>
          <p className="mt-1 max-w-md text-sm text-muted-foreground">
            告诉我你的求职意向，我会自动搜索岗位、匹配简历、优化简历并生成面试题。
            试试输入「河南 国企 Java」开始吧！
          </p>
        </div>
      </div>
    );
  }

  return (
    <ScrollArea className="flex-1">
      <div className="flex flex-col gap-4 p-4 lg:p-6">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} onRetry={onRetry} />
        ))}
        <div ref={bottomRef} />
      </div>
    </ScrollArea>
  );
}
