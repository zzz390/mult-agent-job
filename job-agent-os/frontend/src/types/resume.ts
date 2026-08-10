/** Resume types (matches backend schemas/resume.py) */

export interface EducationInfo {
  school: string | null;
  degree: string | null;
  major: string | null;
  graduation: string | null;
}

export interface ProjectExp {
  name: string;
  description: string | null;
  tech_stack: string[];
}

export interface InternExp {
  company: string;
  role: string | null;
  duration: string | null;
  description: string | null;
}

export interface StructuredResumeData {
  name?: string | null;
  education?: EducationInfo | null;
  skills?: string[];
  projects?: ProjectExp[];
  internships?: InternExp[];
  certifications?: string[];
}

export interface ResumeResponse {
  id: string;
  title: string;
  version: string;
  file_type: string | null;
  structured_data: StructuredResumeData | Record<string, unknown>;
  target_direction: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ResumeUpdate {
  title?: string | null;
  structured_data?: Record<string, unknown> | null;
  is_active?: boolean | null;
}
