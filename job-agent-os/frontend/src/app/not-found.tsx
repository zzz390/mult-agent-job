import Link from "next/link";
import { Compass } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 p-8 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-muted">
        <Compass className="h-8 w-8 text-muted-foreground" />
      </div>
      <div>
        <h2 className="text-lg font-semibold">页面不存在</h2>
        <p className="mt-1 max-w-md text-sm text-muted-foreground">
          你访问的页面不存在或已被移除。
        </p>
      </div>
      <Button asChild variant="outline">
        <Link href="/chat">返回对话</Link>
      </Button>
    </div>
  );
}
