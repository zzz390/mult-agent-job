/** Interview API */

import { api } from "./client";
import type { InterviewQuestion } from "@/types/session";

/** Re-export InterviewQuestion as GeneratedQuestion for backward compatibility. */
export type GeneratedQuestion = InterviewQuestion;

export interface QuestionGenerateRequest {
  job_id: string;
  resume_id?: string | null;
  question_types?: string[];
  difficulty?: "easy" | "medium" | "hard" | "mixed";
  count?: number;
}

export interface GenerationTaskResponse {
  task_id: string;
  status: "processing" | "completed" | "failed" | string;
  result: {
    status: string;
    job_title: string | null;
    questions: GeneratedQuestion[];
  } | null;
}

export function generateQuestions(data: QuestionGenerateRequest) {
  return api.post<{ task_id: string; status: string }>("/v1/interview/questions", data);
}

export function getGenerationResult(taskId: string) {
  return api.get<GenerationTaskResponse>(`/v1/interview/questions/${taskId}`);
}
