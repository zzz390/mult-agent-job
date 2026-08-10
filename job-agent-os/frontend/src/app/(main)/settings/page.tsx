"use client";

import { useCallback, useEffect, useState } from "react";
import { Coins, Loader2, Settings as SettingsIcon, User as UserIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { AgentDonutChart, DailyUsageChart } from "@/components/settings/TokenUsageCharts";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { toast } from "@/stores/toast-store";
import * as usersApi from "@/lib/api/users";
import type { UserProfile } from "@/lib/api/users";
import * as monitoringApi from "@/lib/api/monitoring";
import type { TokenUsageResponse } from "@/lib/api/monitoring";

function Section({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border bg-card p-5 shadow-sm">
      <div className="mb-4 flex items-center gap-2 text-sm font-semibold">
        {icon}
        {title}
      </div>
      {children}
    </section>
  );
}

export default function SettingsPage() {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [tokenUsage, setTokenUsage] = useState<TokenUsageResponse | null>(null);
  const [loading, setLoading] = useState(true);

  // Profile form
  const [username, setUsername] = useState("");
  const [phone, setPhone] = useState("");
  const [saving, setSaving] = useState(false);

  // Preferences form
  const [prefRegion, setPrefRegion] = useState("");
  const [prefDirection, setPrefDirection] = useState("");
  const [prefCompanyType, setPrefCompanyType] = useState("");
  const [savingPrefs, setSavingPrefs] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [u, tu] = await Promise.all([
        usersApi.getCurrentUser(),
        monitoringApi.getTokenUsage(7).catch(() => null),
      ]);
      setUser(u);
      setTokenUsage(tu);
      setUsername(u.username);
      setPhone(u.phone ?? "");
      const prefs = u.preferences ?? {};
      setPrefRegion(typeof prefs.default_region === "string" ? prefs.default_region : "");
      setPrefDirection(typeof prefs.default_direction === "string" ? prefs.default_direction : "");
      setPrefCompanyType(typeof prefs.default_company_type === "string" ? prefs.default_company_type : "");
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const saveProfile = async () => {
    setSaving(true);
    try {
      const updated = await usersApi.updateCurrentUser({
        username: username.trim() || undefined,
        phone: phone.trim() || null,
      });
      setUser(updated);
      toast.success("个人信息已保存");
    } catch (e) {
      toast.error("保存失败", e instanceof Error ? e.message : undefined);
    } finally {
      setSaving(false);
    }
  };

  const savePreferences = async () => {
    setSavingPrefs(true);
    try {
      const updated = await usersApi.updateCurrentUser({
        preferences: {
          ...(user?.preferences ?? {}),
          default_region: prefRegion.trim(),
          default_direction: prefDirection.trim(),
          default_company_type: prefCompanyType.trim(),
        },
      });
      setUser(updated);
      toast.success("偏好设置已保存");
    } catch (e) {
      toast.error("保存失败", e instanceof Error ? e.message : undefined);
    } finally {
      setSavingPrefs(false);
    }
  };

  const budgetTotal = user?.token_budget_daily ?? 0;
  const budgetUsed = user?.token_used_today ?? 0;
  const budgetPercent = budgetTotal > 0 ? Math.min(100, Math.round((budgetUsed / budgetTotal) * 100)) : 0;

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Header */}
      <div className="border-b bg-card px-4 py-4 lg:px-6">
        <div className="flex items-center gap-2">
          <SettingsIcon className="h-5 w-5 text-primary" />
          <h1 className="text-lg font-bold">设置</h1>
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-4 lg:p-6">
        {loading ? (
          <div className="mx-auto max-w-3xl space-y-4">
            <Skeleton className="h-48 rounded-xl" />
            <Skeleton className="h-64 rounded-xl" />
            <Skeleton className="h-48 rounded-xl" />
          </div>
        ) : (
          <div className="mx-auto max-w-3xl space-y-5">
            {/* Profile */}
            <Section icon={<UserIcon className="h-4 w-4 text-primary" />} title="个人信息">
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label>用户名</Label>
                  <Input value={username} onChange={(e) => setUsername(e.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <Label>邮箱（不可修改）</Label>
                  <Input value={user?.email ?? ""} disabled />
                </div>
                <div className="space-y-1.5">
                  <Label>手机号</Label>
                  <Input
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder="可选"
                  />
                </div>
              </div>
              <Button onClick={saveProfile} disabled={saving} className="mt-4">
                {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                保存
              </Button>
            </Section>

            {/* Token usage */}
            <Section icon={<Coins className="h-4 w-4 text-primary" />} title="Token 用量">
              {/* Budget progress */}
              <div className="mb-5">
                <div className="mb-1.5 flex items-baseline justify-between">
                  <span className="text-xs text-muted-foreground">今日预算</span>
                  <span className="text-xs text-muted-foreground">
                    {budgetUsed.toLocaleString()} / {budgetTotal.toLocaleString()}
                  </span>
                </div>
                <Progress value={budgetPercent} />
                <p className="mt-1 text-[11px] text-muted-foreground">
                  已使用 {budgetPercent}%，剩余{" "}
                  {tokenUsage?.budget_remaining?.toLocaleString() ??
                    Math.max(budgetTotal - budgetUsed, 0).toLocaleString()}{" "}
                  Tokens
                </p>
              </div>

              <div className="grid gap-5 sm:grid-cols-2">
                <div>
                  <p className="mb-2 text-xs font-semibold text-muted-foreground">按 Agent 分布</p>
                  <AgentDonutChart data={tokenUsage?.by_agent ?? []} />
                </div>
                <div>
                  <p className="mb-2 text-xs font-semibold text-muted-foreground">每日用量趋势</p>
                  <DailyUsageChart data={tokenUsage?.by_day ?? []} />
                  {tokenUsage && (
                    <p className="mt-2 text-[11px] text-muted-foreground">
                      累计 {tokenUsage.total_tokens.toLocaleString()} Tokens · 约 $
                      {tokenUsage.total_cost_usd.toFixed(4)}
                    </p>
                  )}
                </div>
              </div>
            </Section>

            {/* Preferences */}
            <Section icon={<SettingsIcon className="h-4 w-4 text-primary" />} title="求职偏好">
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="space-y-1.5">
                  <Label>默认搜索地区</Label>
                  <Input
                    value={prefRegion}
                    onChange={(e) => setPrefRegion(e.target.value)}
                    placeholder="如：郑州"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label>默认方向</Label>
                  <Input
                    value={prefDirection}
                    onChange={(e) => setPrefDirection(e.target.value)}
                    placeholder="如：Java"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label>默认企业类型</Label>
                  <Input
                    value={prefCompanyType}
                    onChange={(e) => setPrefCompanyType(e.target.value)}
                    placeholder="如：国企"
                  />
                </div>
              </div>
              <Button onClick={savePreferences} disabled={savingPrefs} className="mt-4">
                {savingPrefs && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                保存偏好
              </Button>
            </Section>

            {/* Appearance */}
            <Section icon={<SettingsIcon className="h-4 w-4 text-primary" />} title="外观">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium">主题模式</p>
                  <p className="text-xs text-muted-foreground">切换浅色 / 深色外观</p>
                </div>
                <ThemeToggle />
              </div>
            </Section>
          </div>
        )}
      </div>
    </div>
  );
}

