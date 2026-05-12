import { ArrowRight, Calculator, Check, ChevronLeft, ChevronRight, Info, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  ErrorState,
  Field,
  Input,
  LoadingState,
  Select,
} from "@/components/ui";
import { useAgents, useCompareScenarios, useEstimateAgent } from "@/hooks";
import type {
  AgentProfile,
  AgentType,
  Channel,
  CostBreakdown,
  InteractionProfile,
} from "@/types/api";
import { formatCurrency, formatNumber, titleCase, toNum } from "@/utils/format";

const AGENT_TYPES: { value: AgentType; label: string }[] = [
  { value: "declarative_instruction", label: "Declarative · instruction" },
  { value: "declarative_public", label: "Declarative · public web" },
  { value: "declarative_tenant", label: "Declarative · tenant graph" },
  { value: "copilot_studio_custom", label: "Copilot Studio · custom" },
  { value: "copilot_studio_declarative", label: "Copilot Studio · declarative" },
  { value: "foundry_native", label: "Foundry · native" },
  { value: "foundry_hosted", label: "Foundry · hosted" },
  { value: "hybrid_studio_foundry", label: "Hybrid Studio + Foundry" },
];

const CHANNELS: { value: Channel; label: string }[] = [
  { value: "m365_copilot", label: "M365 Copilot" },
  { value: "teams_copilot_extension", label: "Teams · Copilot extension" },
  { value: "teams_standalone", label: "Teams · standalone" },
  { value: "web_chat", label: "Web chat" },
  { value: "custom_channel", label: "Custom channel" },
  { value: "copilot_chat_free", label: "Copilot Chat (free)" },
];

const MODELS = [
  { value: "gpt_5_4_mini", label: "GPT-5.4 mini" },
  { value: "gpt_5_4", label: "GPT-5.4" },
  { value: "gpt_5_4_long", label: "GPT-5.4 (long context)" },
  { value: "gpt_5_4_pro", label: "GPT-5.4 Pro (frontier)" },
];

const SEARCH_TIERS = [
  { value: "", label: "Disabled" },
  { value: "basic", label: "Basic" },
  { value: "standard", label: "Standard" },
  { value: "storage_optimized", label: "Storage-optimized" },
];

const DEFAULT_PROFILE: AgentProfile = {
  agent_id: "scenario-blank",
  agent_name: "Blank scenario",
  agent_type: "copilot_studio_custom",
  channel: "m365_copilot",
  primary_model_id: "gpt_5_4_mini",
  prompt_caching_enabled: false,
  uses_batch_api: false,
  uses_tenant_graph: false,
  uses_public_web: false,
  uses_ai_search: false,
  ai_search_tier: null,
  reasoning_model: false,
  licensed_user_count: 100,
  unlicensed_user_count: 0,
  external_user_count: 0,
  avg_interactions_per_user_per_month: 30,
  avg_credits_per_interaction: 5,
  avg_tokens_input_per_interaction: 1500,
  avg_tokens_output_per_interaction: 500,
  cache_hit_rate: 0.2,
};

const DEFAULT_USAGE: InteractionProfile = {
  classic_answers_per_interaction: 0,
  generative_answers_per_interaction: 1,
  agent_actions_per_interaction: 0,
  tenant_graph_grounding_per_interaction: 0,
  agent_flow_actions_per_interaction: 0,
  ai_tool_basic_responses_per_interaction: 0,
  ai_tool_standard_responses_per_interaction: 0,
  ai_tool_premium_responses_per_interaction: 0,
  content_pages_per_interaction: 0,
};

function useDebounced<T>(value: T, delay = 400): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return v;
}

export default function WhatIfModeler() {
  const agents = useAgents();
  const [step, setStep] = useState(1);
  const [baseId, setBaseId] = useState<string>("");
  const [profile, setProfile] = useState<AgentProfile>(DEFAULT_PROFILE);
  const [usage, setUsage] = useState<InteractionProfile>(DEFAULT_USAGE);

  const estimate = useEstimateAgent();
  const compare = useCompareScenarios();
  const [breakdown, setBreakdown] = useState<CostBreakdown | null>(null);

  const debouncedProfile = useDebounced(profile, 400);
  const debouncedUsage = useDebounced(usage, 400);

  // Initialize from base agent
  function selectBase(id: string) {
    setBaseId(id);
    if (!id) {
      setProfile(DEFAULT_PROFILE);
      return;
    }
    const a = agents.data?.find((x) => x.agent_id === id);
    if (!a) return;
    setProfile({
      agent_id: a.agent_id,
      agent_name: a.agent_name,
      agent_type: (a.agent_type as AgentType) ?? "copilot_studio_custom",
      channel: (a.channel as Channel) ?? "m365_copilot",
      primary_model_id: a.primary_model_id ?? "gpt_5_4_mini",
      prompt_caching_enabled: a.prompt_caching_enabled,
      uses_batch_api: a.uses_batch_api,
      uses_tenant_graph: a.uses_tenant_graph,
      uses_public_web: a.uses_public_web,
      uses_ai_search: a.uses_ai_search,
      ai_search_tier: a.ai_search_tier,
      ai_search_units: a.ai_search_units,
      reasoning_model: a.reasoning_model,
      licensed_user_count: a.licensed_user_count,
      unlicensed_user_count: a.unlicensed_user_count,
      external_user_count: a.external_user_count,
      avg_interactions_per_user_per_month: a.avg_interactions_per_user_per_month ?? 30,
      avg_credits_per_interaction: a.avg_credits_per_interaction ?? 5,
      avg_tokens_input_per_interaction: a.avg_tokens_input_per_interaction ?? 1500,
      avg_tokens_output_per_interaction: a.avg_tokens_output_per_interaction ?? 500,
      cache_hit_rate: a.cache_hit_rate ?? 0,
      hosted_vcpu: a.hosted_vcpu,
      hosted_memory_gib: a.hosted_memory_gib,
      hosted_hours_per_month: a.hosted_hours_per_month,
      cost_center: a.cost_center,
      owner: a.owner,
      environment: a.environment,
    });
  }

  // Live estimate effect
  useEffect(() => {
    const id = profile.agent_id || "scenario-blank";
    estimate.mutate(
      {
        agentId: id,
        payload: {
          profile: debouncedProfile,
          usage: debouncedUsage,
          period_months: 1,
          scenario_name: "What-If",
        },
      },
      { onSuccess: (data) => setBreakdown(data) },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedProfile, debouncedUsage]);

  function runCompare() {
    compare.mutate({
      base_profile: profile,
      usage,
      period_months: 1,
    });
  }

  const agentOptions = useMemo(
    () => [
      { value: "", label: "Blank scenario" },
      ...(agents.data ?? []).map((a) => ({
        value: a.agent_id,
        label: `${a.agent_name} · ${titleCase(String(a.agent_type))}`,
      })),
    ],
    [agents.data],
  );

  return (
    <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
      <div className="xl:col-span-2 flex flex-col gap-5">
        <Stepper step={step} onChange={setStep} />

        {step === 1 && (
          <Card>
            <CardHeader
              title="Step 1 · Choose a starting point"
              subtitle="Pick an existing agent to clone, or start blank."
            />
            <CardBody className="flex flex-col gap-4">
              <Field label="Base agent">
                <Select
                  options={agentOptions}
                  value={baseId}
                  onChange={(e) => selectBase(e.target.value)}
                />
              </Field>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Field label="Scenario name">
                  <Input
                    value={profile.agent_name ?? ""}
                    onChange={(e) =>
                      setProfile((p) => ({ ...p, agent_name: e.target.value }))
                    }
                  />
                </Field>
                <Field label="Agent type">
                  <Select
                    options={AGENT_TYPES}
                    value={profile.agent_type}
                    onChange={(e) =>
                      setProfile((p) => ({
                        ...p,
                        agent_type: e.target.value as AgentType,
                      }))
                    }
                  />
                </Field>
                <Field label="Channel">
                  <Select
                    options={CHANNELS}
                    value={profile.channel}
                    onChange={(e) =>
                      setProfile((p) => ({
                        ...p,
                        channel: e.target.value as Channel,
                      }))
                    }
                  />
                </Field>
                <Field label="Cost center">
                  <Input
                    value={profile.cost_center ?? ""}
                    onChange={(e) =>
                      setProfile((p) => ({ ...p, cost_center: e.target.value }))
                    }
                  />
                </Field>
              </div>
            </CardBody>
          </Card>
        )}

        {step === 2 && (
          <Card>
            <CardHeader
              title="Step 2 · Usage profile"
              subtitle="User population and per-interaction profile drive volume."
            />
            <CardBody className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <NumField
                label="Licensed users (M365 Copilot)"
                value={profile.licensed_user_count ?? 0}
                onChange={(v) => setProfile((p) => ({ ...p, licensed_user_count: v }))}
              />
              <NumField
                label="Unlicensed internal users"
                value={profile.unlicensed_user_count ?? 0}
                onChange={(v) => setProfile((p) => ({ ...p, unlicensed_user_count: v }))}
              />
              <NumField
                label="External users"
                value={profile.external_user_count ?? 0}
                onChange={(v) => setProfile((p) => ({ ...p, external_user_count: v }))}
              />
              <NumField
                label="Interactions / user / month"
                value={profile.avg_interactions_per_user_per_month ?? 0}
                onChange={(v) =>
                  setProfile((p) => ({ ...p, avg_interactions_per_user_per_month: v }))
                }
              />
              <NumField
                label="Avg credits / interaction"
                step={0.5}
                value={profile.avg_credits_per_interaction ?? 0}
                onChange={(v) =>
                  setProfile((p) => ({ ...p, avg_credits_per_interaction: v }))
                }
              />
              <NumField
                label="Avg tokens IN / interaction"
                value={profile.avg_tokens_input_per_interaction ?? 0}
                onChange={(v) =>
                  setProfile((p) => ({ ...p, avg_tokens_input_per_interaction: v }))
                }
              />
              <NumField
                label="Avg tokens OUT / interaction"
                value={profile.avg_tokens_output_per_interaction ?? 0}
                onChange={(v) =>
                  setProfile((p) => ({ ...p, avg_tokens_output_per_interaction: v }))
                }
              />
              <SliderField
                label={`Cache hit rate · ${Math.round((profile.cache_hit_rate ?? 0) * 100)}%`}
                value={profile.cache_hit_rate ?? 0}
                min={0}
                max={1}
                step={0.05}
                onChange={(v) => setProfile((p) => ({ ...p, cache_hit_rate: v }))}
              />
            </CardBody>
          </Card>
        )}

        {step === 3 && (
          <Card>
            <CardHeader
              title="Step 3 · Model & grounding"
              subtitle="Tune the cost levers."
            />
            <CardBody className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Field label="Primary model">
                <Select
                  options={MODELS}
                  value={profile.primary_model_id ?? "gpt_5_4_mini"}
                  onChange={(e) =>
                    setProfile((p) => ({ ...p, primary_model_id: e.target.value }))
                  }
                />
              </Field>
              <Field label="AI Search tier">
                <Select
                  options={SEARCH_TIERS}
                  value={profile.ai_search_tier ?? ""}
                  onChange={(e) =>
                    setProfile((p) => ({
                      ...p,
                      ai_search_tier: e.target.value || null,
                      uses_ai_search: !!e.target.value,
                    }))
                  }
                />
              </Field>
              <ToggleField
                label="Prompt caching"
                hint="Cuts repeated-prompt input cost up to 90%."
                value={!!profile.prompt_caching_enabled}
                onChange={(v) => setProfile((p) => ({ ...p, prompt_caching_enabled: v }))}
              />
              <ToggleField
                label="Batch API"
                hint="50% discount for non-realtime workloads."
                value={!!profile.uses_batch_api}
                onChange={(v) => setProfile((p) => ({ ...p, uses_batch_api: v }))}
              />
              <ToggleField
                label="Tenant Graph grounding"
                hint="Adds 10 credits / RAG event."
                value={!!profile.uses_tenant_graph}
                onChange={(v) => setProfile((p) => ({ ...p, uses_tenant_graph: v }))}
              />
              <ToggleField
                label="Public web grounding"
                value={!!profile.uses_public_web}
                onChange={(v) => setProfile((p) => ({ ...p, uses_public_web: v }))}
              />
              <ToggleField
                label="Reasoning model"
                hint="Stacks 100 premium tool credits / 10 responses."
                value={!!profile.reasoning_model}
                onChange={(v) => setProfile((p) => ({ ...p, reasoning_model: v }))}
              />
              <NumField
                label="Tenant graph events / interaction"
                step={0.1}
                value={usage.tenant_graph_grounding_per_interaction ?? 0}
                onChange={(v) =>
                  setUsage((u) => ({
                    ...u,
                    tenant_graph_grounding_per_interaction: v,
                  }))
                }
              />
            </CardBody>
          </Card>
        )}

        <div className="flex items-center justify-between">
          <Button
            variant="ghost"
            disabled={step === 1}
            onClick={() => setStep((s) => Math.max(1, s - 1))}
          >
            <ChevronLeft size={14} /> Back
          </Button>
          {step < 3 ? (
            <Button variant="primary" onClick={() => setStep((s) => s + 1)}>
              Next <ChevronRight size={14} />
            </Button>
          ) : (
            <Button variant="primary" onClick={runCompare} loading={compare.isPending}>
              <Calculator size={14} /> Compare scenarios
            </Button>
          )}
        </div>

        {compare.data && <ScenarioCompareTable data={compare.data} />}
      </div>

      {/* Sticky live results */}
      <div className="xl:sticky xl:top-20 self-start flex flex-col gap-4">
        <LiveResults breakdown={breakdown} loading={estimate.isPending} error={estimate.error} />
      </div>
    </div>
  );
}

function Stepper({ step, onChange }: { step: number; onChange: (n: number) => void }) {
  const steps = [
    { n: 1, label: "Base agent" },
    { n: 2, label: "Usage profile" },
    { n: 3, label: "Model & grounding" },
  ];
  return (
    <div className="flex items-center gap-3">
      {steps.map((s, i) => (
        <div key={s.n} className="flex items-center gap-3 flex-1">
          <button
            type="button"
            onClick={() => onChange(s.n)}
            className={`flex items-center gap-2 ${
              s.n === step ? "text-fabric-blue-dark" : "text-fabric-gray-130"
            }`}
          >
            <span
              className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold ${
                s.n < step
                  ? "bg-fabric-success text-white"
                  : s.n === step
                    ? "bg-fabric-blue text-white"
                    : "bg-fabric-gray-20 text-fabric-gray-130"
              }`}
            >
              {s.n < step ? <Check size={12} /> : s.n}
            </span>
            <span className="text-sm font-medium hidden sm:inline">{s.label}</span>
          </button>
          {i < steps.length - 1 && (
            <div className="flex-1 h-px bg-fabric-gray-30" />
          )}
        </div>
      ))}
    </div>
  );
}

function NumField({
  label,
  value,
  onChange,
  step = 1,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  step?: number;
}) {
  return (
    <Field label={label}>
      <Input
        type="number"
        value={value}
        step={step}
        onChange={(e) => onChange(Number(e.target.value) || 0)}
      />
    </Field>
  );
}

function SliderField({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
}) {
  return (
    <Field label={label}>
      <input
        type="range"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-fabric-blue"
      />
    </Field>
  );
}

function ToggleField({
  label,
  hint,
  value,
  onChange,
}: {
  label: string;
  hint?: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-start gap-2 cursor-pointer p-3 border border-fabric-gray-30 rounded-md bg-white hover:bg-fabric-gray-10 transition-colors">
      <input
        type="checkbox"
        checked={value}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 accent-fabric-blue"
      />
      <span className="flex-1">
        <span className="block text-sm font-medium text-fabric-gray-190">{label}</span>
        {hint && <span className="block text-xs text-fabric-gray-130 mt-0.5">{hint}</span>}
      </span>
    </label>
  );
}

function LiveResults({
  breakdown,
  loading,
  error,
}: {
  breakdown: CostBreakdown | null;
  loading: boolean;
  error: unknown;
}) {
  return (
    <Card>
      <CardHeader
        title="Live estimate"
        subtitle="Recalculates 400ms after each input change"
        action={loading && <RefreshCw size={14} className="animate-spin text-fabric-blue" />}
      />
      <CardBody>
        {error ? (
          <ErrorState error={error} />
        ) : !breakdown ? (
          <LoadingState message="Calculating…" />
        ) : (
          <div className="flex flex-col gap-4">
            <div>
              <div className="text-[10px] uppercase tracking-wide text-fabric-gray-130 font-semibold">
                Total monthly
              </div>
              <div className="text-3xl font-semibold text-fabric-gray-190 tabular-nums">
                {formatCurrency(breakdown.total_monthly_usd, { decimals: 0 })}
              </div>
              <div className="text-[11px] text-fabric-gray-130 mt-1">
                Range {formatCurrency(breakdown.low_estimate_usd, { decimals: 0 })} –{" "}
                {formatCurrency(breakdown.high_estimate_usd, { decimals: 0 })} ·{" "}
                <Badge tone="neutral" size="xs">
                  {titleCase(breakdown.confidence)} confidence
                </Badge>
              </div>
            </div>

            <div className="border-t border-fabric-gray-20 pt-3 flex flex-col gap-1.5 text-sm">
              <Row label="License" value={formatCurrency(breakdown.license_cost_total_usd)} />
              <Row
                label={`Copilot Credits${breakdown.b2e_zero_rated ? " (B2E zero-rated)" : ""}`}
                value={formatCurrency(
                  toNum(breakdown.credits_cost_payg_usd) +
                    toNum(breakdown.credits_cost_pack_usd),
                )}
              />
              <Row label="Azure OpenAI" value={formatCurrency(breakdown.azure_openai_cost_usd)} />
              <Row
                label="Foundry tools"
                value={formatCurrency(breakdown.foundry_tools_cost_usd)}
              />
              <Row label="AI Search" value={formatCurrency(breakdown.ai_search_cost_usd)} />
              <Row
                label="Hosted compute"
                value={formatCurrency(breakdown.hosted_agent_compute_usd)}
              />
            </div>

            <div className="border-t border-fabric-gray-20 pt-3 grid grid-cols-2 gap-3">
              <Mini
                label="Cost / interaction"
                value={formatCurrency(breakdown.cost_per_interaction_usd, { decimals: 4 })}
              />
              <Mini
                label="Cost / active user"
                value={formatCurrency(breakdown.cost_per_active_user_monthly_usd, { decimals: 2 })}
              />
              <Mini
                label="Tokens / month"
                value={formatNumber(breakdown.tokens_monthly, { compact: true })}
              />
              <Mini
                label="Credits charged"
                value={formatNumber(breakdown.credits_charged, { compact: true })}
              />
            </div>

            {breakdown.notes.length > 0 && (
              <div className="border-t border-fabric-gray-20 pt-3 text-[11px] text-fabric-gray-130 flex gap-2">
                <Info size={12} className="flex-shrink-0 mt-0.5" />
                <ul className="space-y-1">
                  {breakdown.notes.slice(0, 3).map((n, i) => (
                    <li key={i}>{n}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-fabric-gray-130 text-xs">{label}</span>
      <span className="font-medium text-fabric-gray-190 tabular-nums">{value}</span>
    </div>
  );
}
function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-fabric-gray-10 rounded-md p-2 border border-fabric-gray-20">
      <div className="text-[10px] uppercase tracking-wide text-fabric-gray-130 font-semibold">
        {label}
      </div>
      <div className="text-sm font-semibold text-fabric-gray-190 tabular-nums mt-0.5">
        {value}
      </div>
    </div>
  );
}

function ScenarioCompareTable({ data }: { data: ReturnType<typeof useCompareScenarios>["data"] }) {
  if (!data) return null;
  if (data.results.length === 0)
    return (
      <Card>
        <EmptyState message="No comparison results." />
      </Card>
    );
  const cheapestName = data.cheapest?.scenario_name;
  return (
    <Card>
      <CardHeader
        title="Scenario comparison"
        subtitle={data.recommendation || "Cheapest option highlighted"}
      />
      <CardBody className="overflow-auto">
        <table className="min-w-full text-sm">
          <thead className="text-xs uppercase tracking-wide text-fabric-gray-130">
            <tr>
              <th className="text-left px-3 py-2">Scenario</th>
              <th className="text-right px-3 py-2">Monthly</th>
              <th className="text-right px-3 py-2">License</th>
              <th className="text-right px-3 py-2">Credits</th>
              <th className="text-right px-3 py-2">Azure</th>
              <th className="text-right px-3 py-2">Per interaction</th>
              <th className="text-left px-3 py-2">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {data.results.map((r) => {
              const isCheapest = r.scenario_name === cheapestName;
              return (
                <tr
                  key={r.scenario_name}
                  className={`border-t border-fabric-gray-20 ${
                    isCheapest ? "bg-emerald-50" : ""
                  }`}
                >
                  <td className="px-3 py-2 font-medium">
                    {r.scenario_name}
                    {isCheapest && (
                      <Badge tone="success" size="xs" className="ml-2">
                        Cheapest <ArrowRight size={10} />
                      </Badge>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums font-semibold">
                    {formatCurrency(r.total_monthly_usd, { decimals: 0 })}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {formatCurrency(r.license_cost_total_usd, { decimals: 0 })}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {formatCurrency(
                      toNum(r.credits_cost_pack_usd) + toNum(r.credits_cost_payg_usd),
                      { decimals: 0 },
                    )}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {formatCurrency(r.azure_total_usd, { decimals: 0 })}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {formatCurrency(r.cost_per_interaction_usd, { decimals: 4 })}
                  </td>
                  <td className="px-3 py-2">
                    <Badge tone="neutral" size="xs">
                      {titleCase(r.confidence)}
                    </Badge>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </CardBody>
    </Card>
  );
}
