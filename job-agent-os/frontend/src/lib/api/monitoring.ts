/** Monitoring API */

import { api } from "./client";

export interface TokenUsageByAgent {
  agent: string;
  tokens: number;
  cost_usd: number;
}

export interface TokenUsageResponse {
  total_tokens: number;
  total_cost_usd: number;
  by_day: { date: string; tokens: number }[];
  by_agent: TokenUsageByAgent[];
  budget_remaining: number;
}

export function getTokenUsage(days = 7) {
  return api.get<TokenUsageResponse>(`/v1/monitoring/token-usage?days=${days}`);
}
