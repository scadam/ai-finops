import { ArrowRight, Bot, Cloud, Coins, DollarSign, Lightbulb, Sparkles } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";
import {
  CreditPoolRing,
  LicenseUtilGauge,
  SpendAreaChart,
  TopAgentsBarChart,
} from "@/components/charts";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  ErrorState,
  KPICard,
  LoadingState,
  ProgressBar,
  effortTone,
  severityTone,
} from "@/components/ui";
import {
  useAnomalies,
  useCostSummary,
  useCostTrends,
  useCredits,
  useDismissOptimisation,
  useLicenses,
  useOptimisations,
} from "@/hooks";
import {
  formatCurrency,
  formatNumber,
  formatPct,
  formatRelativeTime,
  titleCase,
  toNum,
} from "@/utils/format";

export default function Dashboard() {
  const summary = useCostSummary();
  const trends = useCostTrends(6);
  const credits = useCredits();
  const licenses = useLicenses();
  const optimisations = useOptimisations();
  const anomalies = useAnomalies({ acknowledged: false });
  const dismissOpt = useDismissOptimisation();

  const topAgents = useMemo(() => {
    const list = credits.data?.by_agent ?? [];
    return list
      .filter((a) => toNum(a.cost_usd) > 0 || a.credits_charged > 0)
      .map((a) => ({
        name: a.agent_name || a.agent_id || "—",
        cost: toNum(a.cost_usd),
      }));
  }, [credits.data]);

  const licenseAgg = useMemo(() => {
    const all = licenses.data ?? [];
    const totalAssigned = all.reduce((s, l) => s + (l.total_assigned ?? 0), 0);
    const totalActive = all.reduce((s, l) => s + (l.total_active ?? 0), 0);
    const pct = totalAssigned > 0 ? (totalActive / totalAssigned) * 100 : 0;
    return { totalAssigned, totalActive, pct };
  }, [licenses.data]);

  const topAnomalies = (anomalies.data ?? []).slice(0, 5);
  const topOpts = (optimisations.data ?? []).slice(0, 3);

  if (summary.isLoading) return <LoadingState message="Loading FinOps dashboard…" />;
  if (summary.isError)
    return <ErrorState error={summary.error} onRetry={() => summary.refetch()} />;
  const s = summary.data!;

  const budgetPct = Number.isFinite(s.budget_pct) ? s.budget_pct : 0;
  const budgetTone =
    budgetPct >= 100 ? "error" : budgetPct >= 80 ? "warning" : "blue";

  return (
    <div className="flex flex-col gap-5">
      {/* KPI strip */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <div className="flex flex-col gap-2">
          <KPICard
            label="Total AI Spend MTD"
            value={formatCurrency(s.total_monthly_usd, { decimals: 0 })}
            sub={
              toNum(s.budget_amount_usd) > 0
                ? `${formatPct(budgetPct, 0)} of ${formatCurrency(s.budget_amount_usd, { decimals: 0 })}`
                : "no budget set"
            }
            trend={s.mom_change_pct}
            trendLabel="MoM"
            invertTrend
            icon={<DollarSign size={16} />}
          />
          {toNum(s.budget_amount_usd) > 0 && (
            <Card className="px-4 py-2.5">
              <ProgressBar value={budgetPct} tone={budgetTone} showLabel />
            </Card>
          )}
        </div>
        <KPICard
          label="Copilot Credits Billed"
          value={formatNumber(s.credits_billed, { compact: true })}
          sub={`+ ${formatNumber(s.credits_shadow, { compact: true })} shadow (zero-rated)`}
          icon={<Coins size={16} />}
          accent="success"
        />
        <KPICard
          label="Azure AI Consumption"
          value={formatCurrency(s.azure_consumption_usd, { decimals: 0 })}
          sub={s.top_model ? `top model · ${s.top_model}` : "no model usage"}
          icon={<Cloud size={16} />}
        />
        <KPICard
          label="Optimisation Potential"
          value={formatCurrency(s.optimisation_potential_usd, { decimals: 0 })}
          sub={`${s.recommendation_count} recommendation${s.recommendation_count === 1 ? "" : "s"}`}
          icon={<Lightbulb size={16} />}
          accent="warning"
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <Card className="lg:col-span-2">
          <CardHeader
            title="6-month spend trend"
            subtitle="Stacked by meter — license, Copilot Credits, Azure consumption"
          />
          <CardBody>
            {trends.isLoading ? (
              <LoadingState message="Loading trend…" />
            ) : trends.isError ? (
              <ErrorState error={trends.error} onRetry={() => trends.refetch()} />
            ) : (trends.data ?? []).length === 0 ? (
              <EmptyState message="No cost events recorded yet" />
            ) : (
              <SpendAreaChart data={trends.data ?? []} />
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Top agents by credit cost"
            subtitle="Current month, billed credits"
          />
          <CardBody>
            {credits.isLoading ? (
              <LoadingState message="Loading agents…" />
            ) : topAgents.length === 0 ? (
              <EmptyState message="No agent cost data yet" />
            ) : (
              <TopAgentsBarChart data={topAgents} />
            )}
          </CardBody>
        </Card>
      </div>

      {/* Lower row: anomalies + ring/gauge */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Open anomalies"
            subtitle="Unacknowledged cost deviations"
            action={
              <Link
                to="/governance"
                className="text-xs font-medium text-fabric-blue hover:text-fabric-blue-dark inline-flex items-center gap-1"
              >
                View all <ArrowRight size={12} />
              </Link>
            }
          />
          <CardBody className="p-0">
            {anomalies.isLoading ? (
              <LoadingState message="Loading anomalies…" />
            ) : topAnomalies.length === 0 ? (
              <EmptyState
                title="All clear"
                message="No open anomalies right now."
                icon={<Sparkles size={20} />}
              />
            ) : (
              <ul className="divide-y divide-fabric-gray-20">
                {topAnomalies.map((a) => (
                  <li
                    key={a.id}
                    className="px-5 py-3 flex items-center gap-3 hover:bg-fabric-gray-10 transition-colors"
                  >
                    <Badge tone={severityTone(a.severity)} dot>
                      {titleCase(a.severity)}
                    </Badge>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-fabric-gray-190 truncate">
                        {a.title}
                      </div>
                      <div className="text-xs text-fabric-gray-130 truncate">
                        <Bot size={11} className="inline -mt-0.5 mr-1" />
                        {a.affected_agent_name || a.affected_agent_id || "—"} · {a.detector}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-semibold text-fabric-gray-190 tabular-nums">
                        {formatCurrency(a.actual_cost_usd, { decimals: 0 })}
                      </div>
                      <div className="text-[11px] text-fabric-gray-130">
                        {formatRelativeTime(a.detected_at)}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>

        <div className="flex flex-col gap-5">
          <Card>
            <CardHeader title="Credit pool fill" subtitle="Pre-paid pack utilisation" />
            <CardBody>
              {credits.isLoading ? (
                <LoadingState message="Loading…" />
              ) : (
                <CreditPoolRing
                  used={credits.data?.pack_credits_used ?? 0}
                  remaining={credits.data?.pack_credits_remaining ?? 0}
                  centerLabel={`${formatNumber(credits.data?.pack_credits_used ?? 0, { compact: true })} used`}
                />
              )}
            </CardBody>
          </Card>
          <Card>
            <CardHeader
              title="License utilisation"
              subtitle={`${formatNumber(licenseAgg.totalActive)} of ${formatNumber(licenseAgg.totalAssigned)} seats active 7d`}
            />
            <CardBody>
              {licenses.isLoading ? (
                <LoadingState message="Loading…" />
              ) : licenseAgg.totalAssigned === 0 ? (
                <EmptyState message="No license assignments tracked" />
              ) : (
                <LicenseUtilGauge pct={licenseAgg.pct} />
              )}
            </CardBody>
          </Card>
        </div>
      </div>

      {/* Top optimisations */}
      <div className="flex items-end justify-between mt-1">
        <div>
          <h2 className="text-base font-semibold text-fabric-gray-190">
            Top optimisation opportunities
          </h2>
          <p className="text-xs text-fabric-gray-130 mt-0.5">
            Highest savings ranked by monthly impact
          </p>
        </div>
        <Link
          to="/optimisations"
          className="text-xs font-medium text-fabric-blue hover:text-fabric-blue-dark inline-flex items-center gap-1"
        >
          View all <ArrowRight size={12} />
        </Link>
      </div>
      {optimisations.isLoading ? (
        <LoadingState message="Loading recommendations…" />
      ) : topOpts.length === 0 ? (
        <Card>
          <EmptyState
            title="No recommendations available"
            message="Re-run the recommender after seeding cost events."
          />
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {topOpts.map((o) => {
            const savingPct =
              toNum(o.before_cost_usd) > 0
                ? ((toNum(o.before_cost_usd) - toNum(o.after_cost_usd)) /
                    toNum(o.before_cost_usd)) *
                  100
                : 0;
            return (
              <Card key={o.id} className="flex flex-col">
                <CardBody className="flex-1 flex flex-col gap-3">
                  <div className="flex items-center justify-between">
                    <Badge tone="blue">{titleCase(String(o.category))}</Badge>
                    <Badge tone={effortTone(o.implementation_effort)}>
                      {titleCase(String(o.implementation_effort))} effort
                    </Badge>
                  </div>
                  <h3 className="text-sm font-semibold text-fabric-gray-190 leading-snug">
                    {o.title}
                  </h3>
                  <p className="text-xs text-fabric-gray-130 line-clamp-3">
                    {o.description}
                  </p>
                  <div className="mt-auto pt-2">
                    <div className="text-2xl font-semibold text-fabric-success tabular-nums">
                      {formatCurrency(o.monthly_saving_usd, { decimals: 0 })}
                      <span className="text-xs font-normal text-fabric-gray-130 ml-1">
                        / month
                      </span>
                    </div>
                    {savingPct > 0 && (
                      <div className="text-[11px] text-fabric-gray-130 mt-0.5">
                        {formatPct(savingPct, 0)} reduction · confidence{" "}
                        {Math.round((o.confidence ?? 0) * 100)}%
                      </div>
                    )}
                    <ProgressBar
                      value={Math.round((o.confidence ?? 0) * 100)}
                      tone="blue"
                      className="mt-2"
                    />
                  </div>
                </CardBody>
                <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-fabric-gray-20 bg-fabric-gray-10 rounded-b-md">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      dismissOpt.mutate({ id: o.id, reason: "dismissed-from-dashboard" })
                    }
                  >
                    Dismiss
                  </Button>
                  <Button variant="primary" size="sm">
                    Accept
                  </Button>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
