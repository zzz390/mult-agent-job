"use client";

import { useState } from "react";
import { Loader2, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import * as jobsApi from "@/lib/api/jobs";

interface ManualJobDialogProps {
  onCreated: () => void;
}

export function ManualJobDialog({ onCreated }: ManualJobDialogProps) {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    title: "",
    company: "",
    company_type: "",
    location: "",
    salary_range: "",
    education_required: "",
    skills: "",
    raw_description: "",
    source_url: "",
  });

  const update = (key: keyof typeof form, value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const submit = async () => {
    if (!form.title.trim() || !form.company.trim()) {
      setError("岗位名称和公司不能为空");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await jobsApi.createManualJob({
        title: form.title.trim(),
        company: form.company.trim(),
        company_type: form.company_type.trim() || null,
        location: form.location.trim() || null,
        salary_range: form.salary_range.trim() || null,
        education_required: form.education_required.trim() || null,
        skills_required: form.skills
          .split(/[,，\s]+/)
          .map((s) => s.trim())
          .filter(Boolean),
        raw_description: form.raw_description.trim() || null,
        source_url: form.source_url.trim() || null,
      });
      setOpen(false);
      setForm({
        title: "",
        company: "",
        company_type: "",
        location: "",
        salary_range: "",
        education_required: "",
        skills: "",
        raw_description: "",
        source_url: "",
      });
      onCreated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "创建失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Plus className="mr-2 h-4 w-4" />
          手动录入
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>手动录入岗位</DialogTitle>
          <DialogDescription>
            填写岗位信息，留空字段可稍后补充。
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-3 py-2">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="mj-title">岗位名称 *</Label>
              <Input
                id="mj-title"
                value={form.title}
                onChange={(e) => update("title", e.target.value)}
                placeholder="如：Java 开发工程师"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="mj-company">公司 *</Label>
              <Input
                id="mj-company"
                value={form.company}
                onChange={(e) => update("company", e.target.value)}
                placeholder="如：某某科技有限公司"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="mj-type">公司类型</Label>
              <Input
                id="mj-type"
                value={form.company_type}
                onChange={(e) => update("company_type", e.target.value)}
                placeholder="如：国企"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="mj-location">工作地点</Label>
              <Input
                id="mj-location"
                value={form.location}
                onChange={(e) => update("location", e.target.value)}
                placeholder="如：郑州"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="mj-salary">薪资范围</Label>
              <Input
                id="mj-salary"
                value={form.salary_range}
                onChange={(e) => update("salary_range", e.target.value)}
                placeholder="如：8k-12k"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="mj-edu">学历要求</Label>
              <Input
                id="mj-edu"
                value={form.education_required}
                onChange={(e) => update("education_required", e.target.value)}
                placeholder="如：本科"
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="mj-skills">技能要求（逗号分隔）</Label>
            <Input
              id="mj-skills"
              value={form.skills}
              onChange={(e) => update("skills", e.target.value)}
              placeholder="如：Java, Spring, MySQL"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="mj-desc">岗位描述</Label>
            <Textarea
              id="mj-desc"
              value={form.raw_description}
              onChange={(e) => update("raw_description", e.target.value)}
              placeholder="粘贴 JD 原文..."
              className="min-h-[80px]"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="mj-url">来源链接</Label>
            <Input
              id="mj-url"
              value={form.source_url}
              onChange={(e) => update("source_url", e.target.value)}
              placeholder="https://..."
            />
          </div>
        </div>

        {error && <p className="text-xs text-destructive">{error}</p>}

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            取消
          </Button>
          <Button onClick={submit} disabled={submitting}>
            {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            创建
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
