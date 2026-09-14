"use client";

import { useState } from "react";
import { Loader2, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const QUICK_TEMPLATES = [
  "河南 国企 Java",
  "北京 央企 Python",
  "上海 外企 前端",
  "深圳 大厂 算法",
];

const PLATFORM_OPTIONS = [
  { value: "boss", label: "BOSS 直聘" },
  { value: "guopin", label: "国聘" },
  { value: "niuke", label: "牛客" },
] as const;

export interface ChatSendOptions {
  platforms?: string[];
}

interface ChatInputProps {
  onSend: (content: string, options?: ChatSendOptions) => void;
  disabled?: boolean;
  placeholder?: string;
  /** Platform choices only apply when the message will create a new session. */
  platformSelectionAvailable?: boolean;
}

export function ChatInput({
  onSend,
  disabled,
  placeholder,
  platformSelectionAvailable = true,
}: ChatInputProps) {
  const [value, setValue] = useState("");
  const [platforms, setPlatforms] = useState<string[]>([]);

  const togglePlatform = (platform: string) => {
    setPlatforms((selected) =>
      selected.includes(platform)
        ? selected.filter((item) => item !== platform)
        : [...selected, platform]
    );
  };

  const submit = () => {
    if (!value.trim() || disabled) return;
    onSend(
      value.trim(),
      platforms.length > 0 ? { platforms: [...platforms] } : undefined
    );
    setValue("");
    setPlatforms([]);
  };

  return (
    <div className="border-t bg-card p-4">
      {/* Quick templates */}
      <div className="mb-3 flex flex-wrap gap-2">
        {QUICK_TEMPLATES.map((tpl) => (
          <button
            key={tpl}
            type="button"
            onClick={() => setValue(tpl)}
            disabled={disabled}
            className="rounded-full border bg-background px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-primary hover:text-primary disabled:opacity-50"
          >
            {tpl}
          </button>
        ))}
      </div>

      {/* Optional explicit sources. No selection preserves official-first search. */}
      <div
        className="mb-3 flex flex-wrap items-center gap-2"
        role="group"
        aria-label="扩展招聘平台，可多选"
        aria-describedby="platform-selection-hint"
      >
        <span className="text-xs font-medium text-muted-foreground">
          扩展平台（可多选）
        </span>
        {PLATFORM_OPTIONS.map((platform) => {
          const selected = platforms.includes(platform.value);
          return (
            <button
              key={platform.value}
              type="button"
              onClick={() => togglePlatform(platform.value)}
              disabled={disabled || !platformSelectionAvailable}
              aria-pressed={selected}
              className="rounded-full border px-3 py-1 text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-50 data-[selected=true]:border-primary data-[selected=true]:bg-primary/10 data-[selected=true]:text-primary"
              data-selected={selected}
            >
              {platform.label}
            </button>
          );
        })}
        <span id="platform-selection-hint" className="text-[11px] text-muted-foreground">
          {platformSelectionAvailable
            ? "不选则优先搜索企业官网"
            : "仅新会话可选择平台"}
        </span>
      </div>

      <div className="flex gap-2">
        <Input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder={placeholder || "描述你的求职意向，如：河南省、国企、Java方向..."}
          disabled={disabled}
          className="flex-1"
        />
        <Button onClick={submit} disabled={disabled || !value.trim()} size="icon">
          {disabled ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </Button>
      </div>
    </div>
  );
}
