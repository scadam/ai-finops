// Types mirror /api/v1/* responses defined in src/ai_finops/api/schemas.py
// All money values arrive as strings (Decimal-preserving). Counts are numbers.

export type Money = string;

export type AgentType =
  | "declarative_instruction"
  | "declarative_public"
  | "declarative_tenant"
  | "copilot_studio_custom"
  | "copilot_studio_declarative"
  | "foundry_native"
  | "foundry_hosted"
  | "hybrid_studio_foundry";

export type Channel =
  | "m365_copilot"
  | "teams_copilot_extension"
  | "teams_standalone"
  | "web_chat"
  | "custom_channel"
  | "copilot_chat_free";

export type OptimisationCategory =
  | "license_channel_routing"
  | "model_downshift"
  | "prompt_caching"
  | "batch_api"
  | "ptu_reservation"
  | "graph_grounding_toggle"
  | "classic_answer_fallback"
  | "zombie_ft_model"
  | "idle_endpoint"
  | "ai_search_rightsizing"
  | "license_right_sizing"
  | "pack_vs_payg"
  | "agent_technology_switch";

export type Effort = "low" | "medium" | "high";
export type Severity = "low" | "medium" | "high" | "critical";
export type BudgetStatus = "on_track" | "warning" | "exceeded";

export interface CostSummary {
  total_monthly_usd: Money;
  budget_amount_usd: Money;
  budget_pct: number;
  mom_change_pct: number;
  credits_billed: number;
  credits_shadow: number;
  credits_pack_fill_pct: number;
  azure_consumption_usd: Money;
  top_model: string | null;
  optimisation_potential_usd: Money;
  recommendation_count: number;
  by_meter: Record<string, Money>;
}

export interface CostTrendPoint {
  period: string; // YYYY-MM
  license_cost_usd: Money;
  credits_cost_usd: Money;
  azure_cost_usd: Money;
  total_cost_usd: Money;
}

export interface AgentSummary {
  agent_id: string;
  agent_name: string;
  agent_type: AgentType | string;
  channel: Channel | string;
  build_platform: string;
  owner: string;
  cost_center: string;
  environment: string;
  status: string;
  is_frontier_preview: boolean;
  uses_tenant_graph: boolean;
  uses_public_web: boolean;
  uses_dataverse: boolean;
  uses_ai_search: boolean;
  ai_search_tier: string | null;
  ai_search_units: number;
  primary_model_id: string | null;
  reasoning_model: boolean;
  uses_batch_api: boolean;
  prompt_caching_enabled: boolean;
  fine_tuned_model_id: string | null;
  hosted_vcpu: number;
  hosted_memory_gib: number;
  hosted_hours_per_month: number;
  web_search_transactions: number;
  custom_search_transactions: number;
  code_interpreter_sessions: number;
  file_search_storage_gb: number;
  avg_credits_per_interaction: number | null;
  avg_tokens_input_per_interaction: number | null;
  avg_tokens_output_per_interaction: number | null;
  avg_interactions_per_user_per_month: number | null;
  cache_hit_rate: number;
  licensed_user_count: number;
  unlicensed_user_count: number;
  external_user_count: number;
  active_users_7d: number | null;
  agent_365_registered: boolean;
  agent_365_owner_upn: string | null;
  created_at?: string;
  updated_at?: string;
}

export type AgentDetail = AgentSummary;

export interface Optimisation {
  id: string;
  created_at?: string;
  agent_id: string | null;
  category: OptimisationCategory | string;
  title: string;
  description: string;
  monthly_saving_usd: Money;
  implementation_effort: Effort | string;
  confidence: number; // 0-1
  before_cost_usd: Money;
  after_cost_usd: Money;
  evidence: string;
  action_url?: string | null;
  dismissed?: boolean;
  dismissed_reason?: string | null;
  dismissed_at?: string | null;
}

export interface Budget {
  id: string;
  name: string;
  amount_usd: Money;
  period: string;
  alert_threshold_pct: number;
  scope: string;
  owner: string;
  consumed_usd: Money;
  consumed_pct: number;
  status: BudgetStatus | string;
}

export interface Anomaly {
  id: string;
  detected_at: string;
  severity: Severity | string;
  detector: string;
  title: string;
  description: string;
  affected_agent_id: string | null;
  affected_agent_name: string | null;
  expected_cost_usd: Money;
  actual_cost_usd: Money;
  deviation_pct: number;
  acknowledged: boolean;
  acknowledged_by?: string | null;
  acknowledged_action?: string | null;
  acknowledged_at?: string | null;
}

export interface License {
  license_type: string;
  total_assigned: number;
  total_active: number;
  utilisation_pct: number;
  cost_per_seat_usd: Money;
  monthly_total_usd: Money;
}

export interface CreditUsageByAgent {
  agent_id: string;
  agent_name: string;
  credits_charged: number;
  credits_shadow: number;
  cost_usd: Money;
}

export interface CreditUsage {
  total_credits_charged: number;
  total_credits_zero_rated: number;
  pack_credits_used: number;
  pack_credits_remaining: number;
  payg_overflow_credits: number;
  cost_pack_usd: Money;
  cost_payg_usd: Money;
  cost_total_usd: Money;
  by_agent: CreditUsageByAgent[];
}

export interface RateCardStatusEntry {
  name: string;
  last_refreshed: string;
  is_stale: boolean;
  effective_date: string;
  source_url: string;
}

export interface ExecutiveSummary {
  generated_at: string;
  total_ai_spend_usd: Money;
  by_meter: Record<string, Money>;
  top_optimisations: Optimisation[];
  summary: CostSummary;
}

export interface FocusExportInfo {
  format: string;
  row_count: number;
  columns: string[];
}

// ---- Modeler ----
export interface AgentProfile {
  agent_id?: string;
  agent_name?: string;
  agent_type: AgentType;
  channel: Channel;
  build_platform?: string;
  owner?: string;
  cost_center?: string;
  environment?: string;
  is_frontier_preview?: boolean;
  uses_tenant_graph?: boolean;
  uses_public_web?: boolean;
  uses_dataverse?: boolean;
  uses_ai_search?: boolean;
  ai_search_tier?: string | null;
  ai_search_units?: number;
  primary_model_id?: string | null;
  reasoning_model?: boolean;
  uses_batch_api?: boolean;
  prompt_caching_enabled?: boolean;
  fine_tuned_model_id?: string | null;
  hosted_vcpu?: number;
  hosted_memory_gib?: number;
  hosted_hours_per_month?: number;
  web_search_transactions?: number;
  custom_search_transactions?: number;
  code_interpreter_sessions?: number;
  file_search_storage_gb?: number;
  avg_credits_per_interaction?: number | null;
  avg_tokens_input_per_interaction?: number | null;
  avg_tokens_output_per_interaction?: number | null;
  avg_interactions_per_user_per_month?: number | null;
  cache_hit_rate?: number;
  licensed_user_count?: number;
  unlicensed_user_count?: number;
  external_user_count?: number;
  active_users_7d?: number | null;
  agent_365_registered?: boolean;
  agent_365_owner_upn?: string | null;
}

export interface InteractionProfile {
  classic_answers_per_interaction?: number;
  generative_answers_per_interaction?: number;
  agent_actions_per_interaction?: number;
  tenant_graph_grounding_per_interaction?: number;
  agent_flow_actions_per_interaction?: number;
  ai_tool_basic_responses_per_interaction?: number;
  ai_tool_standard_responses_per_interaction?: number;
  ai_tool_premium_responses_per_interaction?: number;
  content_pages_per_interaction?: number;
}

export interface EstimateRequest {
  profile: AgentProfile;
  usage: InteractionProfile;
  period_months?: number;
  scenario_name?: string;
}

export interface CostBreakdown {
  scenario_name: string;
  period_months: number;
  utilisation_band: string;
  confidence: string;
  license_cost_total_usd: Money;
  license_detail: Array<Record<string, unknown>>;
  credits_charged: number;
  credits_zero_rated: number;
  credits_shadow: number;
  credits_cost_payg_usd: Money;
  credits_cost_pack_usd: Money;
  credits_packs_required: number;
  credits_recommendation: string;
  credits_detail: Record<string, number>;
  b2e_zero_rated: boolean;
  tokens_monthly: number;
  azure_openai_cost_usd: Money;
  foundry_tools_cost_usd: Money;
  ai_search_cost_usd: Money;
  hosted_agent_compute_usd: Money;
  azure_total_usd: Money;
  total_monthly_usd: Money;
  total_annual_usd: Money;
  cost_per_interaction_usd: Money;
  cost_per_active_user_monthly_usd: Money;
  low_estimate_usd: Money;
  high_estimate_usd: Money;
  potential_savings_usd: Money;
  optimisation_recommendations: Optimisation[];
  notes: string[];
}

export interface CompareRequest {
  base_profile: AgentProfile;
  usage: InteractionProfile;
  agent_types?: AgentType[];
  period_months?: number;
}

export interface CompareResponse {
  cheapest: CostBreakdown | null;
  recommendation: string;
  results: CostBreakdown[];
}
