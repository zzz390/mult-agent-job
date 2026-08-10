/** Applications API */

import { api } from "./client";
import type {
  ApplicationResponse,
  ApplicationStatistics,
  ApplicationStatusUpdate,
  KanbanView,
} from "@/types/application";

export function getKanban() {
  return api.get<KanbanView>("/v1/applications/kanban");
}

export function getStatistics() {
  return api.get<ApplicationStatistics>("/v1/applications/statistics");
}

export function updateApplicationStatus(
  applicationId: string,
  data: ApplicationStatusUpdate
) {
  return api.patch<ApplicationResponse>(
    `/v1/applications/${applicationId}/status`,
    data
  );
}

export function getApplication(applicationId: string) {
  return api.get<ApplicationResponse>(`/v1/applications/${applicationId}`);
}
