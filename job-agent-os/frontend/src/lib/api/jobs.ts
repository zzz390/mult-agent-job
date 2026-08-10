/** Jobs API */

import { api } from "./client";
import type { PaginatedData } from "@/types/api";
import type { JobFilters, JobResponse, ManualJobCreate } from "@/types/job";

export function listJobs(
  params: JobFilters & { page?: number; page_size?: number } = {}
) {
  const query = new URLSearchParams();
  if (params.platform) query.set("platform", params.platform);
  if (params.location) query.set("location", params.location);
  if (params.keyword) query.set("keyword", params.keyword);
  if (params.status) query.set("status", params.status);
  if (params.page) query.set("page", String(params.page));
  if (params.page_size) query.set("page_size", String(params.page_size));
  const qs = query.toString();
  return api.get<PaginatedData<JobResponse>>(`/v1/jobs${qs ? `?${qs}` : ""}`);
}

export function getJob(jobId: string) {
  return api.get<JobResponse>(`/v1/jobs/${jobId}`);
}

export function createManualJob(data: ManualJobCreate) {
  return api.post<JobResponse>("/v1/jobs/manual", data);
}

export function triggerJobSearch(data: {
  query_text?: string;
  platforms?: string[];
}) {
  return api.post<{ session_id: string }>("/v1/jobs/search", data);
}
