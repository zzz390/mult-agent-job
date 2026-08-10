"use client";

import { useCallback, useRef, useState } from "react";
import { FileUp, Loader2, Upload } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import * as resumesApi from "@/lib/api/resumes";

const ACCEPTED = [
  "application/pdf",
  "text/markdown",
  "text/plain",
  "text/x-markdown",
];

interface ResumeUploaderProps {
  onUploaded: () => void;
}

export function ResumeUploader({ onUploaded }: ResumeUploaderProps) {
  const [dragging, setDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [direction, setDirection] = useState("");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const acceptFile = useCallback((f: File | undefined | null) => {
    if (!f) return;
    if (!ACCEPTED.includes(f.type) && !/\.(pdf|md|markdown|txt)$/i.test(f.name)) {
      setError("仅支持 PDF / Markdown / 纯文本格式");
      return;
    }
    setError(null);
    setFile(f);
    if (!title) setTitle(f.name.replace(/\.(pdf|md|markdown|txt)$/i, ""));
  }, [title]);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    acceptFile(e.dataTransfer.files?.[0]);
  }, [acceptFile]);

  const upload = async () => {
    if (!file) return;
    if (!title.trim()) {
      setError("请填写简历标题");
      return;
    }
    setUploading(true);
    setError(null);
    try {
      await resumesApi.uploadResume({
        file,
        title: title.trim(),
        target_direction: direction.trim() || undefined,
      });
      setFile(null);
      setTitle("");
      setDirection("");
      onUploaded();
    } catch (e) {
      setError(e instanceof Error ? e.message : "上传失败");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="rounded-xl border bg-card p-4 shadow-sm">
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
        <FileUp className="h-4 w-4 text-primary" />
        上传简历
      </div>

      {/* Drop zone */}
      <div
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-6 text-center transition-colors",
          dragging
            ? "border-primary bg-primary/5"
            : "border-muted-foreground/25 hover:border-primary/50"
        )}
      >
        <Upload className="h-6 w-6 text-muted-foreground" />
        {file ? (
          <p className="text-sm font-medium text-primary">{file.name}</p>
        ) : (
          <>
            <p className="text-sm text-muted-foreground">
              拖拽文件到此处，或点击选择
            </p>
            <p className="text-[11px] text-muted-foreground">支持 PDF / Markdown / TXT</p>
          </>
        )}
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.md,.markdown,.txt,application/pdf,text/markdown,text/plain"
          className="hidden"
          onChange={(e) => acceptFile(e.target.files?.[0])}
        />
      </div>

      {/* Meta fields */}
      {file && (
        <div className="mt-3 space-y-2.5">
          <div className="space-y-1.5">
            <Label htmlFor="rv-title">简历标题 *</Label>
            <Input
              id="rv-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="如：Java 方向简历 v1"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="rv-direction">目标方向（可选）</Label>
            <Input
              id="rv-direction"
              value={direction}
              onChange={(e) => setDirection(e.target.value)}
              placeholder="如：Java 后端开发"
            />
          </div>
        </div>
      )}

      {error && <p className="mt-2 text-xs text-destructive">{error}</p>}

      {file && (
        <Button onClick={upload} disabled={uploading} className="mt-3 w-full">
          {uploading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          确认上传
        </Button>
      )}
    </div>
  );
}
