"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bot,
  MessageSquare,
  KanbanSquare,
  Briefcase,
  FileText,
  GraduationCap,
  Settings,
} from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/chat", label: "对话", icon: MessageSquare },
  { href: "/kanban", label: "看板", icon: KanbanSquare },
  { href: "/jobs", label: "岗位", icon: Briefcase },
  { href: "/resume", label: "简历", icon: FileText },
  { href: "/interview", label: "面试", icon: GraduationCap },
  { href: "/settings", label: "设置", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-full w-16 flex-col items-center border-r bg-card py-4 lg:w-56 lg:items-stretch lg:px-3">
      {/* Logo */}
      <div className="mb-8 flex items-center justify-center gap-2 lg:justify-start lg:px-2">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary">
          <Bot className="h-5 w-5 text-primary-foreground" />
        </div>
        <span className="hidden text-base font-bold lg:block">Job Agent OS</span>
      </div>

      {/* Nav */}
      <nav className="flex flex-1 flex-col gap-1">
        {navItems.map((item) => {
          const active = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center justify-center gap-3 rounded-lg px-2 py-2.5 text-sm font-medium transition-colors lg:justify-start lg:px-3",
                active
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              )}
            >
              <item.icon className="h-5 w-5 shrink-0" />
              <span className="hidden lg:block">{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
