"use client";

import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import type { JobFilters as JobFiltersType } from "@/types/job";

const PLATFORMS = [
  { value: "", label: "全部平台" },
  { value: "boss", label: "BOSS直聘" },
  { value: "guopin", label: "国聘" },
  { value: "niuke", label: "牛客" },
  { value: "manual", label: "手动录入" },
];

const STATUSES = [
  { value: "", label: "全部状态" },
  { value: "active", label: "有效" },
  { value: "expired", label: "已过期" },
];

interface JobFiltersProps {
  filters: JobFiltersType;
  onChange: (filters: JobFiltersType) => void;
}

export function JobFilters({ filters, onChange }: JobFiltersProps) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {/* Keyword search */}
      <div className="relative min-w-[200px] flex-1">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={filters.keyword ?? ""}
          onChange={(e) => onChange({ ...filters, keyword: e.target.value })}
          placeholder="搜索岗位 / 公司 / 技能..."
          className="pl-9"
        />
      </div>

      {/* Location */}
      <Input
        value={filters.location ?? ""}
        onChange={(e) => onChange({ ...filters, location: e.target.value })}
        placeholder="地区，如：郑州"
        className="w-36"
      />

      {/* Platform */}
      <select
        value={filters.platform ?? ""}
        onChange={(e) =>
          onChange({ ...filters, platform: e.target.value || undefined })
        }
        className="h-10 rounded-md border border-input bg-background px-3 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring"
      >
        {PLATFORMS.map((p) => (
          <option key={p.value} value={p.value}>
            {p.label}
          </option>
        ))}
      </select>

      {/* Status */}
      <select
        value={filters.status ?? ""}
        onChange={(e) =>
          onChange({ ...filters, status: e.target.value || undefined })
        }
        className="h-10 rounded-md border border-input bg-background px-3 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring"
      >
        {STATUSES.map((s) => (
          <option key={s.value} value={s.value}>
            {s.label}
          </option>
        ))}
      </select>
    </div>
  );
}
