import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type {
  AgentDetail,
  AgentSummary,
  Anomaly,
  Budget,
  CompareRequest,
  CompareResponse,
  CostBreakdown,
  CostSummary,
  CostTrendPoint,
  CreditUsage,
  EstimateRequest,
  ExecutiveSummary,
  FocusExportInfo,
  License,
  Optimisation,
  RateCardStatusEntry,
} from "@/types/api";

const COMMON = { staleTime: 30_000, gcTime: 5 * 60_000 };

export function useCostSummary() {
  return useQuery<CostSummary>({
    queryKey: ["cost", "summary"],
    queryFn: async () => (await apiClient.get<CostSummary>("/cost/summary")).data,
    ...COMMON,
  });
}

export function useCostTrends(months = 6) {
  return useQuery<CostTrendPoint[]>({
    queryKey: ["cost", "trends", months],
    queryFn: async () =>
      (await apiClient.get<CostTrendPoint[]>("/cost/trends", { params: { months } })).data,
    ...COMMON,
  });
}

export interface AgentsFilter {
  environment?: string;
  cost_center?: string;
  agent_type?: string;
}

export function useAgents(filters: AgentsFilter = {}) {
  return useQuery<AgentSummary[]>({
    queryKey: ["agents", filters],
    queryFn: async () =>
      (await apiClient.get<AgentSummary[]>("/agents", { params: filters })).data,
    ...COMMON,
  });
}

export function useAgent(agentId: string | null) {
  return useQuery<AgentDetail>({
    queryKey: ["agent", agentId],
    enabled: !!agentId,
    queryFn: async () =>
      (await apiClient.get<AgentDetail>(`/agents/${agentId}`)).data,
    ...COMMON,
  });
}

export interface OptimisationFilter {
  category?: string;
  effort?: string;
  min_saving?: number;
  include_dismissed?: boolean;
}

export function useOptimisations(filters: OptimisationFilter = {}) {
  return useQuery<Optimisation[]>({
    queryKey: ["optimisations", filters],
    queryFn: async () =>
      (await apiClient.get<Optimisation[]>("/optimisations", { params: filters })).data,
    ...COMMON,
  });
}

export function useDismissOptimisation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, reason }: { id: string; reason: string }) =>
      (await apiClient.post(`/optimisations/${id}/dismiss`, { reason })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["optimisations"] });
      qc.invalidateQueries({ queryKey: ["cost", "summary"] });
    },
  });
}

export function useBudgets() {
  return useQuery<Budget[]>({
    queryKey: ["budgets"],
    queryFn: async () => (await apiClient.get<Budget[]>("/budgets")).data,
    ...COMMON,
  });
}

export interface CreateBudgetInput {
  name: string;
  amount_usd: number | string;
  period?: string;
  alert_threshold_pct?: number;
  scope?: string;
  owner?: string;
}

export function useCreateBudget() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: CreateBudgetInput) =>
      (await apiClient.post("/budgets", input)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["budgets"] }),
  });
}

export interface AnomaliesFilter {
  severity?: string;
  acknowledged?: boolean;
}

export function useAnomalies(filters: AnomaliesFilter = {}) {
  return useQuery<Anomaly[]>({
    queryKey: ["anomalies", filters],
    queryFn: async () =>
      (await apiClient.get<Anomaly[]>("/anomalies", { params: filters })).data,
    ...COMMON,
  });
}

export function useAcknowledgeAnomaly() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      action,
      by,
    }: {
      id: string;
      action: string;
      by: string;
    }) =>
      (await apiClient.post(`/anomalies/${id}/acknowledge`, { action, by })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["anomalies"] }),
  });
}

export function useLicenses() {
  return useQuery<License[]>({
    queryKey: ["licenses"],
    queryFn: async () => (await apiClient.get<License[]>("/licenses")).data,
    ...COMMON,
  });
}

export function useCredits() {
  return useQuery<CreditUsage>({
    queryKey: ["credits"],
    queryFn: async () => (await apiClient.get<CreditUsage>("/credits")).data,
    ...COMMON,
  });
}

export function useRateCardStatus() {
  return useQuery<RateCardStatusEntry[]>({
    queryKey: ["rate-cards", "status"],
    queryFn: async () =>
      (await apiClient.get<RateCardStatusEntry[]>("/rate-cards/refresh-status")).data,
    ...COMMON,
  });
}

export function useExecutiveSummary() {
  return useQuery<ExecutiveSummary>({
    queryKey: ["reports", "executive-summary"],
    queryFn: async () =>
      (await apiClient.get<ExecutiveSummary>("/reports/executive-summary")).data,
    ...COMMON,
  });
}

export function useFocusExportInfo() {
  return useQuery<FocusExportInfo>({
    queryKey: ["reports", "focus-export"],
    queryFn: async () =>
      (await apiClient.get<FocusExportInfo>("/reports/focus-export")).data,
    ...COMMON,
  });
}

export function useEstimateAgent() {
  return useMutation({
    mutationFn: async ({
      agentId,
      payload,
    }: {
      agentId: string;
      payload: EstimateRequest;
    }) =>
      (await apiClient.post<CostBreakdown>(`/agents/${agentId}/estimate`, payload)).data,
  });
}

export function useCompareScenarios() {
  return useMutation({
    mutationFn: async (payload: CompareRequest) =>
      (await apiClient.post<CompareResponse>(`/scenarios/compare`, payload)).data,
  });
}
