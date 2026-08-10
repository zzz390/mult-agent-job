/** Application types (matches backend schemas/application.py) */

export type ApplicationStatus =
  | "pending"
  | "applied"
  | "written_test"
  | "round1"
  | "round2"
  | "hr_interview"
  | "offer"
  | "rejected";

export interface ApplicationResponse {
  id: string;
  job_id: string;
  resume_id: string;
  status: ApplicationStatus;
  stage: string;
  match_score: number | null;
  match_report: Record<string, unknown> | null;
  priority: "high" | "medium" | "low" | string;
  notes: string | null;
  applied_at: string | null;
  next_follow_up: string | null;
  created_at: string;
}

export interface KanbanView {
  pending: ApplicationResponse[];
  applied: ApplicationResponse[];
  written_test: ApplicationResponse[];
  round1: ApplicationResponse[];
  round2: ApplicationResponse[];
  hr_interview: ApplicationResponse[];
  offer: ApplicationResponse[];
  rejected: ApplicationResponse[];
  statistics: Record<string, number>;
}

export interface ApplicationStatistics {
  total_applications: number;
  by_status: Record<string, number>;
  by_platform: Record<string, number>;
  pass_rate: number;
  avg_match_score: number;
  stage_conversion: Record<string, number>;
}

export interface ApplicationStatusUpdate {
  status: ApplicationStatus;
  stage?: string | null;
  notes?: string | null;
  next_follow_up?: string | null;
}

/** Column order for the kanban board (matches backend state machine). */
export const KANBAN_COLUMNS: { key: ApplicationStatus; label: string }[] = [
  { key: "pending", label: "待投递" },
  { key: "applied", label: "已投递" },
  { key: "written_test", label: "笔试" },
  { key: "round1", label: "一面" },
  { key: "round2", label: "二面" },
  { key: "hr_interview", label: "HR面" },
  { key: "offer", label: "Offer" },
  { key: "rejected", label: "已淘汰" },
];
