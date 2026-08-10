/** Resumes API */

import { api, getAccessToken, refreshTokenFn } from "./client";
import { ApiError } from "@/types/api";
import type { PaginatedData } from "@/types/api";
import type { ResumeResponse, ResumeUpdate } from "@/types/resume";

/** Upload a resume file (multipart/form-data). */
export async function uploadResume(data: {
  file: File;
  title: string;
  target_direction?: string;
}): Promise<ResumeResponse> {
  const formData = new FormData();
  formData.append("file", data.file);
  formData.append("title", data.title);
  if (data.target_direction) {
    formData.append("target_direction", data.target_direction);
  }

  const token = getAccessToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let res = await fetch("/v1/resumes", {
    method: "POST",
    headers,
    body: formData,
  });

  // Handle 401 -> attempt token refresh once, then retry
  if (res.status === 401) {
    const newToken = await refreshTokenFn();
    if (newToken) {
      headers["Authorization"] = `Bearer ${newToken}`;
      res = await fetch("/v1/resumes", {
        method: "POST",
        headers,
        body: formData,
      });
    } else {
      throw new ApiError(40100, "登录已过期，请重新登录", 401);
    }
  }

  let json: { code: number; message: string; data: ResumeResponse };
  try {
    json = await res.json();
  } catch {
    throw new ApiError(res.status, `上传失败 (HTTP ${res.status})`, res.status);
  }
  if (json.code !== 0) {
    throw new ApiError(json.code, json.message || "上传失败", res.status);
  }
  return json.data;
}

export function listResumes(params: { page?: number; page_size?: number } = {}) {
  const query = new URLSearchParams();
  if (params.page) query.set("page", String(params.page));
  if (params.page_size) query.set("page_size", String(params.page_size));
  const qs = query.toString();
  return api.get<PaginatedData<ResumeResponse>>(`/v1/resumes${qs ? `?${qs}` : ""}`);
}

export function getResume(resumeId: string) {
  return api.get<ResumeResponse>(`/v1/resumes/${resumeId}`);
}

export function updateResume(resumeId: string, data: ResumeUpdate) {
  return api.patch<ResumeResponse>(`/v1/resumes/${resumeId}`, data);
}

export function deleteResume(resumeId: string) {
  return api.delete<null>(`/v1/resumes/${resumeId}`);
}
