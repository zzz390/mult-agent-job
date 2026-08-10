"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Bell } from "lucide-react";
import { Button } from "@/components/ui/button";
import * as approvalsApi from "@/lib/api/approvals";

const POLL_INTERVAL = 10000;

export function NotificationBell() {
  const router = useRouter();
  const [pendingCount, setPendingCount] = useState(0);

  useEffect(() => {
    let mounted = true;

    const fetchPending = () => {
      approvalsApi
        .listApprovals({ status: "pending" })
        .then((list) => {
          if (mounted) setPendingCount(list.length);
        })
        .catch(() => undefined);
    };

    fetchPending();
    const timer = setInterval(fetchPending, POLL_INTERVAL);

    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, []);

  return (
    <Button
      variant="ghost"
      size="icon"
      className="relative"
      title={pendingCount > 0 ? `${pendingCount} 个待审批事项` : "暂无待审批事项"}
      onClick={() => router.push("/chat")}
    >
      <Bell className="h-4 w-4" />
      {pendingCount > 0 && (
        <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-bold text-destructive-foreground">
          {pendingCount > 99 ? "99+" : pendingCount}
        </span>
      )}
    </Button>
  );
}
