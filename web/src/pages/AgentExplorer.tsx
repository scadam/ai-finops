import { ChevronRight, Sliders } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  DataTable,
  type DataTableColumn,
  EmptyState,
  ErrorState,
  Field,
  LoadingState,
  ProgressBar,
  Select,
  SlideOver,
  statusTone,
} from "@/components/ui";
import { useAgent, useAgents, useCredits, useOptimisations } from "@/hooks";
import type { AgentSummary } from "@/types/api";
import { formatCurrency, formatNumber, titleCase, toNum } from "@/utils/format";

const ENV_OPTIONS = [
  { value: "", label: "All environments" },
  { value: "prod", label: "Production" },
  { value: "staging", label: "Staging" },
  { value: "dev", label: "Development" },
];

const TYPE_OPTIONS = [
  { value: "", label: "All agent types" },
  { value: "declarative_instruction", label: "Declarative · instruction" },
  { value: "declarative_public", label: "Declarative · public web" },
  { value: "declarative_tenant", label: "Declarative · tenant graph" },
  { value: "copilot_studio_custom", label: "Copilot Studio · custom" },
  { value: "copilot_studio_declarative", label: "Copilot Studio · declarative" },
  { value: "foundry_native", label: "Foundry · native" },
  { value: "foundry_hosted", label: "Foundry · hosted" },
  { value: "hybrid_studio_foundry", label: "Hybrid Studio + Foundry" },
];

function optimisationScore(a: AgentSummary): number {
  let score = 50;
  if (a.prompt_caching_enabled) score += 15;
  if (a.uses_batch_api) score += 10;
  if (a.reasoning_model) score -= 10;
  if ((a.cache_hit_rate ?? 0) > 0.5) score += 10;
  if ((a.active_users_7d ?? 0) === 0 && a.licensed_user_count > 0) score -= 20;
  if (a.uses_tenant_graph && a.channel === "m365_copilot") score += 5;
  return Math.max(0, Math.min(100, score));
}

function scoreTone(s: number) {
  if (s >= 75) return "success" as const;
  if (s >= 50) return "blue" as const;
  if (s >= 25) return "warning" as const;
  return "error" as const;
}

export default function AgentExplorer() {
  const [filters, setFilters] = useState({
    environment: "",
    cost_center: "",
    agent_type: "",
  });
  const [selected, setSelected] = useState<string | null>(null);

  const agents = useAgents({
    environment: filters.environment || undefined,
    cost_center: filters.cost_center || undefined,
    agent_type: filters.agent_type || undefined,
  });
  const credits = useCredits();

  const costByAgent = useMemo(() => {
    const map = new Map<string, { cost: number; credits: number }>();
    for (const c of credits.data?.by_agent ?? []) {
      map.set(c.agent_id, { cost: toNum(c.cost_usd), credits: c.credits_charged });
    }
    return map;
  }, [credits.data]);

  const ccOptions = useMemo(() => {
    const set = new Set<string>();
    (agents.data ?? []).forEach((a) => a.cost_center && set.add(a.cost_center));
    return [
      { value: "", label: "All cost centers" },
      ...Array.from(set).sort().map((v) => ({ value: v, label: v })),
    ];
  }, [agents.data]);

  const columns: DataTableColumn<AgentSummary>[] = [
    {
      id: "name",
      header: "Agent",
      sortable: true,
      accessor: (r) => r.agent_name,
      cell: (r) => (
        <div className="flex flex-col">
          <span className="font-medium">{r.agent_name || r.agent_id}</span>
          <span className="text-[11px] text-fabric-gray-130">
            {r.cost_center || "—"} · owner {r.owner || "—"}
          </span>
        </div>
      ),
    },
    {
      id: "agent_type",
      header: "Type",
      sortable: true,
      accessor: (r) => r.agent_type,
      cell: (r) => (
        <span className="text-xs text-fabric-gray-160">{titleCase(String(r.agent_type))}</span>
      ),
    },
    {
      id: "channel",
      header: "Channel",
      sortable: true,
      accessor: (r) => r.channel,
      cell: (r) => <span className="text-xs">{titleCase(String(r.channel))}</span>,
    },
    {
      id: "cost",
      header: "Monthly cost",
      sortable: true,
      align: "right",
      accessor: (r) => costByAgent.get(r.agent_id)?.cost ?? 0,
      cell: (r) =>
        formatCurrency(costByAgent.get(r.agent_id)?.cost ?? 0, { decimals: 0 }),
    },
    {
      id: "cpi",
      header: "Cost/interaction",
      sortable: true,
      align: "right",
      accessor: (r) => {
        const cost = costByAgent.get(r.agent_id)?.cost ?? 0;
        const interactions =
          (r.avg_interactions_per_user_per_month ?? 0) *
          ((r.licensed_user_count ?? 0) + (r.unlicensed_user_count ?? 0));
        return interactions > 0 ? cost / interactions : 0;
      },
      cell: (r) => {
        const cost = costByAgent.get(r.agent_id)?.cost ?? 0;
        const interactions =
          (r.avg_interactions_per_user_per_month ?? 0) *
          ((r.licensed_user_count ?? 0) + (r.unlicensed_user_count ?? 0));
        return interactions > 0
          ? formatCurrency(cost / interactions, { decimals: 4 })
          : "—";
      },
    },
    {
      id: "credits",
      header: "Credits",
      sortable: true,
      align: "right",
      accessor: (r) => costByAgent.get(r.agent_id)?.credits ?? 0,
      cell: (r) => formatNumber(costByAgent.get(r.agent_id)?.credits ?? 0, { compact: true }),
    },
    {
      id: "score",
      header: "Optimisation score",
      sortable: true,
      accessor: (r) => optimisationScore(r),
      cell: (r) => {
        const s = optimisationScore(r);
        return (
          <div className="w-32">
            <ProgressBar value={s} tone={scoreTone(s)} showLabel />
          </div>
        );
      },
    },
    {
      id: "status",
      header: "Status",
      sortable: true,
      accessor: (r) => r.status,
      cell: (r) => (
        <Badge tone={statusTone(r.status)} dot>
          {titleCase(r.status)}
        </Badge>
      ),
    },
    {
      id: "chevron",
      header: "",
      accessor: () => "",
      cell: () => <ChevronRight size={14} className="text-fabric-gray-130" />,
      width: "32px",
    },
  ];

  return (
    <div className="flex flex-col gap-5">
      <Card>
        <CardHeader title="Filters" subtitle="Narrow the agent inventory" />
        <CardBody className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Field label="Environment">
            <Select
              options={ENV_OPTIONS}
              value={filters.environment}
              onChange={(e) =>
                setFilters((f) => ({ ...f, environment: e.target.value }))
              }
            />
          </Field>
          <Field label="Cost center">
            <Select
              options={ccOptions}
              value={filters.cost_center}
              onChange={(e) =>
                setFilters((f) => ({ ...f, cost_center: e.target.value }))
              }
            />
          </Field>
          <Field label="Agent type">
            <Select
              options={TYPE_OPTIONS}
              value={filters.agent_type}
              onChange={(e) =>
                setFilters((f) => ({ ...f, agent_type: e.target.value }))
              }
            />
          </Field>
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="Agent inventory"
          subtitle={`${agents.data?.length ?? 0} agent${agents.data?.length === 1 ? "" : "s"} matching filters`}
        />
        <CardBody>
          {agents.isLoading ? (
            <LoadingState message="Loading agents…" />
          ) : agents.isError ? (
            <ErrorState error={agents.error} onRetry={() => agents.refetch()} />
          ) : (
            <DataTable
              data={agents.data ?? []}
              columns={columns}
              rowKey={(r) => r.agent_id}
              onRowClick={(r) => setSelected(r.agent_id)}
              searchable
              searchPlaceholder="Search agent name, owner…"
              initialSort={{ id: "cost", dir: "desc" }}
              emptyMessage="No agents match the current filters"
            />
          )}
        </CardBody>
      </Card>

      <AgentDrawer agentId={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

function AgentDrawer({
  agentId,
  onClose,
}: {
  agentId: string | null;
  onClose: () => void;
}) {
  const agent = useAgent(agentId);
  const recs = useOptimisations({ include_dismissed: false });
  const credits = useCredits();
  const open = !!agentId;

  const detail = agent.data;
  const costInfo = agentId
    ? credits.data?.by_agent.find((a) => a.agent_id === agentId)
    : null;

  const agentRecs = (recs.data ?? []).filter((r) => r.agent_id === agentId);

  return (
    <SlideOver
      open={open}
      onClose={onClose}
      title={detail?.agent_name ?? "Agent details"}
      subtitle={detail ? `${titleCase(String(detail.agent_type))} · ${titleCase(String(detail.channel))}` : ""}
      width="xl"
      footer={
        agentId && (
          <>
            <Button variant="ghost" onClick={onClose}>Close</Button>
            <Link to="/modeler">
              <Button variant="primary">
                <Sliders size={14} /> Run What-If
              </Button>
            </Link>
          </>
        )
      }
    >
      {!agentId ? null : agent.isLoading ? (
        <LoadingState />
      ) : agent.isError || !detail ? (
        <ErrorState error={agent.error} />
      ) : (
        <div className="flex flex-col gap-5">
          <section className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Stat label="Owner" value={detail.owner || "—"} />
            <Stat label="Cost center" value={detail.cost_center || "—"} />
            <Stat label="Environment" value={detail.environment} />
            <Stat label="Build platform" value={titleCase(detail.build_platform) || "—"} />
            <Stat
              label="Licensed users"
              value={formatNumber(detail.licensed_user_count)}
            />
            <Stat
              label="Unlicensed users"
              value={formatNumber(detail.unlicensed_user_count)}
            />
            <Stat
              label="External users"
              value={formatNumber(detail.external_user_count)}
            />
            <Stat
              label="Active 7d"
              value={detail.active_users_7d != null ? formatNumber(detail.active_users_7d) : "—"}
            />
          </section>

          <section>
            <h3 className="text-sm font-semibold text-fabric-gray-190 mb-2">
              Cost &amp; usage
            </h3>
            <div className="overflow-hidden rounded-md border border-fabric-gray-30">
              <table className="w-full text-sm">
                <tbody className="divide-y divide-fabric-gray-20">
                  <KV
                    k="Monthly credit cost"
                    v={formatCurrency(costInfo?.cost_usd ?? 0, { decimals: 2 })}
                  />
                  <KV k="Credits charged" v={formatNumber(costInfo?.credits_charged ?? 0)} />
                  <KV k="Credits shadow (zero-rated)" v={formatNumber(costInfo?.credits_shadow ?? 0)} />
                  <KV
                    k="Avg credits / interaction"
                    v={detail.avg_credits_per_interaction != null ? String(detail.avg_credits_per_interaction) : "—"}
                  />
                  <KV
                    k="Avg tokens (in / out) / interaction"
                    v={`${detail.avg_tokens_input_per_interaction ?? "—"} / ${detail.avg_tokens_output_per_interaction ?? "—"}`}
                  />
                  <KV
                    k="Cache hit rate"
                    v={`${(toNum(detail.cache_hit_rate) * 100).toFixed(1)}%`}
                  />
                  <KV k="Primary model" v={detail.primary_model_id || "—"} />
                  <KV k="Reasoning model" v={detail.reasoning_model ? "Yes" : "No"} />
                  <KV k="Prompt caching" v={detail.prompt_caching_enabled ? "Enabled" : "Disabled"} />
                  <KV k="Batch API" v={detail.uses_batch_api ? "Yes" : "No"} />
                  <KV k="Tenant graph grounding" v={detail.uses_tenant_graph ? "Yes" : "No"} />
                  <KV k="Public web grounding" v={detail.uses_public_web ? "Yes" : "No"} />
                  <KV
                    k="AI Search"
                    v={
                      detail.uses_ai_search
                        ? `${detail.ai_search_tier ?? "tier"} · ${detail.ai_search_units} units`
                        : "Not used"
                    }
                  />
                </tbody>
              </table>
            </div>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-fabric-gray-190 mb-2">
              Recommendations
            </h3>
            {agentRecs.length === 0 ? (
              <EmptyState message="No recommendations for this agent." />
            ) : (
              <ul className="flex flex-col gap-2">
                {agentRecs.map((r) => (
                  <li
                    key={r.id}
                    className="border border-fabric-gray-30 rounded-md p-3 bg-fabric-gray-10"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-sm font-semibold text-fabric-gray-190">
                          {r.title}
                        </div>
                        <div className="text-xs text-fabric-gray-130 mt-0.5">
                          {r.description}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-sm font-semibold text-fabric-success tabular-nums">
                          {formatCurrency(r.monthly_saving_usd, { decimals: 0 })}/mo
                        </div>
                        <Badge tone="blue" size="xs">
                          {titleCase(String(r.implementation_effort))} effort
                        </Badge>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}
    </SlideOver>
  );
}

function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="bg-fabric-gray-10 rounded-md p-3 border border-fabric-gray-20">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-fabric-gray-130">
        {label}
      </div>
      <div className="text-sm font-medium text-fabric-gray-190 mt-1 truncate">
        {value}
      </div>
    </div>
  );
}

function KV({ k, v }: { k: string; v: ReactNode }) {
  return (
    <tr>
      <td className="px-3 py-2 text-xs font-medium text-fabric-gray-130 w-1/2">{k}</td>
      <td className="px-3 py-2 text-sm text-fabric-gray-190 tabular-nums">{v}</td>
    </tr>
  );
}
