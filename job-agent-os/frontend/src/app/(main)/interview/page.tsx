"use client";

import { useState } from "react";
import { GraduationCap } from "lucide-react";
import { QuestionGenerator } from "@/components/interview/QuestionGenerator";
import { QuestionList } from "@/components/interview/QuestionList";
import type { GeneratedQuestion } from "@/lib/api/interview";

export default function InterviewPage() {
  const [questions, setQuestions] = useState<GeneratedQuestion[]>([]);
  const [jobTitle, setJobTitle] = useState<string | null>(null);

  const handleGenerated = (qs: GeneratedQuestion[], title: string | null) => {
    setQuestions(qs);
    setJobTitle(title);
  };

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Header */}
      <div className="border-b bg-card px-4 py-4 lg:px-6">
        <div className="flex items-center gap-2">
          <GraduationCap className="h-5 w-5 text-primary" />
          <h1 className="text-lg font-bold">面试准备</h1>
          {jobTitle && (
            <span className="text-xs text-muted-foreground">目标岗位：{jobTitle}</span>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-4 lg:p-6">
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[360px_1fr]">
          {/* Left: generator */}
          <div>
            <QuestionGenerator onGenerated={handleGenerated} />
          </div>

          {/* Right: question list */}
          <div>
            {questions.length === 0 ? (
              <div className="flex h-full min-h-[300px] flex-col items-center justify-center gap-3 rounded-xl border border-dashed text-center">
                <GraduationCap className="h-8 w-8 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">
                  选择岗位并生成面试题，题目将按类型分组展示。
                </p>
              </div>
            ) : (
              <QuestionList questions={questions} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

