/** Job types (matches backend schemas/job.py) */

export interface JobResponse {
  id: string;
  title: string;
  company: string;
  company_type: string | null;
  location: string | null;
  salary_range: string | null;
  education_required: string | null;
  skills_required: string[];
  structured_jd: Record<string, unknown>;
  deadline: string | null;
  source_platform: string;
  source_url: string;
  status: string;
  created_at: string;
}

export interface ManualJobCreate {
  title: string;
  company: string;
  company_type?: string | null;
  location?: string | null;
  salary_range?: string | null;
  education_required?: string | null;
  skills_required?: string[];
  raw_description?: string | null;
  structured_jd?: Record<string, unknown>;
  deadline?: string | null;
  source_url?: string | null;
}

export interface JobFilters {
  platform?: string;
  location?: string;
  keyword?: string;
  status?: string;
}

/** Recommendation item (matches backend schemas/match.py) */
export interface RecommendationItem {
  job: JobResponse;
  match_score: number;
  skill_match: number;
  education_match: number;
  matched_skills: string[];
  missing_skills: string[];
  recommendation_reason: string;
  risk_factors: string[];
}

export interface RecommendationFeedbackRequest {
  job_id: string;
  action: "accept" | "reject" | "interested";
  reason?: string | null;
  adjust_weights?: Record<string, unknown> | null;
}
