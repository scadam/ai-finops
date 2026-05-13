import { Download, ExternalLink, Plus } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { LicenseUtilGauge } from "@/components/charts";
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
  Input,
  LoadingState,
  Modal,
  ProgressBar,
  Select,
  SlideOver,
  Tabs,
  Textarea,
  severityTone,
  statusTone,
} from "@/components/ui";
import {
  useAcknowledgeAnomaly,
  useAnomalies,
  useBudgets,
  useCreateBudget,
  useFocusExportInfo,
  useLicenses,
  useRateCardStatus,
} from "@/hooks";
import type { Anomaly, Budget, License, RateCardStatusEntry } from "@/types/api";
import {
  formatCurrency,
  formatNumber,
  formatPct,
  formatRelativeTime,
  titleCase,
  toNum,
} from "@/utils/format";

const TABS = [
  { id: "budgets", label: "Budgets" },
  { id: "anomalies", label: "Anomalies" },
  { id: "licenses", label: "Licenses" },
  { id: "rate-cards", label: "Rate Card Health" },
  { id: "focus", label: "FOCUS Export" },
];

export default function Governance() {
  const [tab, setTab] = useState("budgets");
  return (
    <div className="flex flex-col gap-5">
      <Card>
        <Tabs tabs={TABS} active={tab} onChange={setTab} className="px-2 pt-2" />
        <CardBody>
          {tab === "budgets" && <BudgetsTab />}
          {tab === "anomalies" && <AnomaliesTab />}
          {tab === "licenses" && <LicensesTab />}
          {tab === "rate-cards" && <RateCardsTab />}
          {tab === "focus" && <FocusTab />}
        </CardBody>
      </Card>
    </div>
  );
}

// ---------- Budgets ----------
function BudgetsTab() {
  const budgets = useBudgets();
  const create = useCreateBudget();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    name: "",
    amount_usd: "",
    period: "monthly",
    alert_threshold_pct: 80,
    scope: "",
    owner: "",
  });

  function reset() {
    setForm({
      name: "",
      amount_usd: "",
      period: "monthly",
      alert_threshold_pct: 80,
      scope: "",
      owner: "",
    });
  }

  function submit() {
    create.mutate(
      {
        name: form.name,
        amount_usd: Number(form.amount_usd) || 0,
        period: form.period,
        alert_threshold_pct: form.alert_threshold_pct,
        scope: form.scope,
        owner: form.owner,
      },
      {
        onSuccess: () => {
          setOpen(false);
          reset();
        },
      },
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-fabric-gray-190">Active budgets</h2>
          <p className="text-xs text-fabric-gray-130 mt-0.5">
            Tracked at tenant, cost-center, agent, or environment scope.
          </p>
        </div>
        <Button variant="primary" onClick={() => setOpen(true)}>
          <Plus size={14} /> Create budget
        </Button>
      </div>

      {budgets.isLoading ? (
        <LoadingState />
      ) : budgets.isError ? (
        <ErrorState error={budgets.error} onRetry={() => budgets.refetch()} />
      ) : (budgets.data ?? []).length === 0 ? (
        <EmptyState
          title="No budgets defined"
          message="Create a budget to track spend against a target."
          action={
            <Button variant="primary" onClick={() => setOpen(true)}>
              <Plus size={14} /> Create budget
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {(budgets.data ?? []).map((b) => (
            <BudgetCard key={b.id} b={b} />
          ))}
        </div>
      )}

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Create budget"
        size="lg"
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              variant="primary"
              loading={create.isPending}
              disabled={!form.name || !form.amount_usd}
              onClick={submit}
            >
              Create
            </Button>
          </>
        }
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Field label="Name" className="md:col-span-2">
            <Input
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="e.g. Marketing AI Q3 cap"
            />
          </Field>
          <Field label="Amount (USD)">
            <Input
              type="number"
              min={0}
              value={form.amount_usd}
              onChange={(e) => setForm((f) => ({ ...f, amount_usd: e.target.value }))}
            />
          </Field>
          <Field label="Period">
            <Select
              value={form.period}
              onChange={(e) => setForm((f) => ({ ...f, period: e.target.value }))}
              options={[
                { value: "monthly", label: "Monthly" },
                { value: "quarterly", label: "Quarterly" },
                { value: "annual", label: "Annual" },
              ]}
            />
          </Field>
          <Field label="Alert threshold (%)">
            <Input
              type="number"
              min={1}
              max={100}
              value={form.alert_threshold_pct}
              onChange={(e) =>
                setForm((f) => ({ ...f, alert_threshold_pct: Number(e.target.value) }))
              }
            />
          </Field>
          <Field
            label="Scope"
            hint="Leave blank for tenant-wide. Examples: cost_center:marketing, agent:agt-001, env:prod"
          >
            <Input
              value={form.scope}
              onChange={(e) => setForm((f) => ({ ...f, scope: e.target.value }))}
              placeholder="cost_center:..."
            />
          </Field>
          <Field label="Owner">
            <Input
              value={form.owner}
              onChange={(e) => setForm((f) => ({ ...f, owner: e.target.value }))}
              placeholder="alice@contoso.com"
            />
          </Field>
        </div>
      </Modal>
    </div>
  );
}

function BudgetCard({ b }: { b: Budget }) {
  const tone =
    b.status === "exceeded" ? "error" : b.status === "warning" ? "warning" : "success";
  return (
    <Card>
      <CardBody className="flex flex-col gap-3">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-sm font-semibold text-fabric-gray-190">{b.name}</div>
            <div className="text-xs text-fabric-gray-130 mt-0.5">
              {b.scope || "tenant"} · {titleCase(b.period)} · owner {b.owner || "—"}
            </div>
          </div>
          <Badge tone={statusTone(b.status)} dot>
            {titleCase(b.status)}
          </Badge>
        </div>
        <div className="text-2xl font-semibold text-fabric-gray-190 tabular-nums">
          {formatCurrency(b.consumed_usd, { decimals: 0 })}
          <span className="text-sm font-normal text-fabric-gray-130 ml-1.5">
            of {formatCurrency(b.amount_usd, { decimals: 0 })}
          </span>
        </div>
        <ProgressBar value={b.consumed_pct} tone={tone} showLabel />
        <div className="text-[11px] text-fabric-gray-130">
          Alerts at {b.alert_threshold_pct}% · {formatPct(b.consumed_pct, 1)} consumed
        </div>
      </CardBody>
    </Card>
  );
}

// ---------- Anomalies ----------
function AnomaliesTab() {
  const [severity, setSeverity] = useState("");
  const [ack, setAck] = useState<"" | "true" | "false">("false");
  const [selected, setSelected] = useState<Anomaly | null>(null);

  const data = useAnomalies({
    severity: severity || undefined,
    acknowledged: ack === "" ? undefined : ack === "true",
  });

  const columns: DataTableColumn<Anomaly>[] = [
    {
      id: "severity",
      header: "Severity",
      sortable: true,
      accessor: (r) => r.severity,
      cell: (r) => (
        <Badge tone={severityTone(r.severity)} dot>
          {titleCase(r.severity)}
        </Badge>
      ),
    },
    {
      id: "title",
      header: "Title",
      sortable: true,
      accessor: (r) => r.title,
      cell: (r) => (
        <div>
          <div className="font-medium text-fabric-gray-190">{r.title}</div>
          <div className="text-[11px] text-fabric-gray-130">
            {r.detector} · {r.affected_agent_name || r.affected_agent_id || "—"}
          </div>
        </div>
      ),
    },
    {
      id: "actual",
      header: "Actual",
      sortable: true,
      align: "right",
      accessor: (r) => toNum(r.actual_cost_usd),
      cell: (r) => formatCurrency(r.actual_cost_usd, { decimals: 0 }),
    },
    {
      id: "deviation",
      header: "Deviation",
      sortable: true,
      align: "right",
      accessor: (r) => r.deviation_pct,
      cell: (r) => formatPct(r.deviation_pct, 0),
    },
    {
      id: "detected",
      header: "Detected",
      sortable: true,
      accessor: (r) => r.detected_at,
      cell: (r) => formatRelativeTime(r.detected_at),
    },
    {
      id: "ack",
      header: "Status",
      accessor: (r) => (r.acknowledged ? "Acknowledged" : "Open"),
      cell: (r) => (
        <Badge tone={r.acknowledged ? "neutral" : "error"} dot>
          {r.acknowledged ? "Acknowledged" : "Open"}
        </Badge>
      ),
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Field label="Severity">
          <Select
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
            options={[
              { value: "", label: "All severities" },
              { value: "critical", label: "Critical" },
              { value: "high", label: "High" },
              { value: "medium", label: "Medium" },
              { value: "low", label: "Low" },
            ]}
          />
        </Field>
        <Field label="Acknowledged">
          <Select
            value={ack}
            onChange={(e) => setAck(e.target.value as "" | "true" | "false")}
            options={[
              { value: "", label: "All" },
              { value: "false", label: "Open only" },
              { value: "true", label: "Acknowledged only" },
            ]}
          />
        </Field>
      </div>

      {data.isLoading ? (
        <LoadingState />
      ) : data.isError ? (
        <ErrorState error={data.error} onRetry={() => data.refetch()} />
      ) : (
        <DataTable
          data={data.data ?? []}
          columns={columns}
          rowKey={(r) => r.id}
          onRowClick={(r) => setSelected(r)}
          initialSort={{ id: "detected", dir: "desc" }}
          emptyMessage="No anomalies match"
        />
      )}

      <AnomalyDrawer anomaly={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

function AnomalyDrawer({
  anomaly,
  onClose,
}: {
  anomaly: Anomaly | null;
  onClose: () => void;
}) {
  const ack = useAcknowledgeAnomaly();
  const [action, setAction] = useState("");
  const [by, setBy] = useState("");

  const open = !!anomaly;
  function submit() {
    if (!anomaly) return;
    ack.mutate(
      { id: anomaly.id, action, by },
      {
        onSuccess: () => {
          onClose();
          setAction("");
          setBy("");
        },
      },
    );
  }

  return (
    <SlideOver
      open={open}
      onClose={onClose}
      title={anomaly?.title}
      subtitle={
        anomaly
          ? `${titleCase(anomaly.severity)} · detected ${formatRelativeTime(anomaly.detected_at)}`
          : ""
      }
      footer={
        anomaly &&
        !anomaly.acknowledged && (
          <>
            <Button variant="ghost" onClick={onClose}>Cancel</Button>
            <Button
              variant="primary"
              loading={ack.isPending}
              disabled={!action || !by}
              onClick={submit}
            >
              Acknowledge
            </Button>
          </>
        )
      }
    >
      {anomaly && (
        <div className="flex flex-col gap-4">
          <p className="text-sm text-fabric-gray-160">{anomaly.description}</p>
          <div className="grid grid-cols-2 gap-3">
            <Stat label="Expected" value={formatCurrency(anomaly.expected_cost_usd)} />
            <Stat label="Actual" value={formatCurrency(anomaly.actual_cost_usd)} />
            <Stat label="Deviation" value={formatPct(anomaly.deviation_pct, 0)} />
            <Stat label="Detector" value={anomaly.detector} />
            <Stat
              label="Agent"
              value={anomaly.affected_agent_name || anomaly.affected_agent_id || "—"}
            />
            <Stat
              label="Acknowledged"
              value={anomaly.acknowledged ? "Yes" : "No"}
            />
          </div>
          {!anomaly.acknowledged ? (
            <div className="border-t border-fabric-gray-20 pt-4 flex flex-col gap-3">
              <h3 className="text-sm font-semibold">Acknowledge</h3>
              <Field label="Action taken">
                <Textarea
                  value={action}
                  onChange={(e) => setAction(e.target.value)}
                  placeholder="e.g. Disabled rogue agent and reset throttle"
                />
              </Field>
              <Field label="By">
                <Input
                  value={by}
                  onChange={(e) => setBy(e.target.value)}
                  placeholder="alice@contoso.com"
                />
              </Field>
            </div>
          ) : (
            <div className="border-t border-fabric-gray-20 pt-4 text-sm text-fabric-gray-130">
              Acknowledged by <strong>{anomaly.acknowledged_by}</strong> ·{" "}
              {formatRelativeTime(anomaly.acknowledged_at)}
              <div className="mt-2 italic">{anomaly.acknowledged_action}</div>
            </div>
          )}
        </div>
      )}
    </SlideOver>
  );
}

// ---------- Licenses ----------
function LicensesTab() {
  const licenses = useLicenses();
  const list = licenses.data ?? [];
  const agg = useMemo(() => {
    const a = list.reduce((s, l) => s + l.total_assigned, 0);
    const t = list.reduce((s, l) => s + l.total_active, 0);
    return { assigned: a, active: t, pct: a > 0 ? (t / a) * 100 : 0 };
  }, [list]);

  if (licenses.isLoading) return <LoadingState />;
  if (licenses.isError)
    return <ErrorState error={licenses.error} onRetry={() => licenses.refetch()} />;
  if (list.length === 0)
    return <EmptyState title="No licenses tracked" message="Assign SKUs via Graph sync." />;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
      <div className="lg:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-4">
        {list.map((l) => (
          <LicenseCard key={l.license_type} l={l} />
        ))}
      </div>
      <Card>
        <CardHeader title="Aggregate utilisation" subtitle="Across all SKUs" />
        <CardBody>
          <LicenseUtilGauge
            pct={agg.pct}
            label={`${formatNumber(agg.active)} / ${formatNumber(agg.assigned)} seats`}
          />
        </CardBody>
      </Card>
    </div>
  );
}

function LicenseCard({ l }: { l: License }) {
  const tone =
    l.utilisation_pct >= 85 ? "success" : l.utilisation_pct >= 60 ? "warning" : "error";
  return (
    <Card>
      <CardBody className="flex flex-col gap-3">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-sm font-semibold text-fabric-gray-190">
              {titleCase(l.license_type)}
            </div>
            <div className="text-xs text-fabric-gray-130 mt-0.5">
              {formatCurrency(l.cost_per_seat_usd)} per seat · {formatCurrency(l.monthly_total_usd, { decimals: 0 })} total
            </div>
          </div>
          <Badge tone={tone}>{formatPct(l.utilisation_pct, 0)}</Badge>
        </div>
        <div className="text-xs text-fabric-gray-130">
          <span className="tabular-nums font-medium text-fabric-gray-190">
            {formatNumber(l.total_active)}
          </span>{" "}
          active of{" "}
          <span className="tabular-nums">{formatNumber(l.total_assigned)}</span>{" "}
          assigned
        </div>
        <ProgressBar value={l.utilisation_pct} tone={tone} />
      </CardBody>
    </Card>
  );
}

// ---------- Rate cards ----------
function RateCardsTab() {
  const rc = useRateCardStatus();
  const columns: DataTableColumn<RateCardStatusEntry>[] = [
    {
      id: "name",
      header: "Rate card",
      sortable: true,
      accessor: (r) => r.name,
      cell: (r) => <span className="font-medium">{titleCase(r.name)}</span>,
    },
    {
      id: "effective",
      header: "Effective date",
      sortable: true,
      accessor: (r) => r.effective_date,
    },
    {
      id: "refreshed",
      header: "Last refreshed",
      sortable: true,
      accessor: (r) => r.last_refreshed,
      cell: (r) => formatRelativeTime(r.last_refreshed),
    },
    {
      id: "stale",
      header: "Status",
      accessor: (r) => (r.is_stale ? "stale" : "fresh"),
      cell: (r) => (
        <Badge tone={r.is_stale ? "warning" : "success"} dot>
          {r.is_stale ? "Stale" : "Fresh"}
        </Badge>
      ),
    },
    {
      id: "source",
      header: "Source",
      accessor: (r) => r.source_url,
      cell: (r) =>
        r.source_url ? (
          <a
            href={r.source_url}
            target="_blank"
            rel="noreferrer"
            className="text-fabric-blue hover:text-fabric-blue-dark inline-flex items-center gap-1 text-xs"
          >
            <ExternalLink size={12} />
            <span className="truncate max-w-xs inline-block align-middle">
              {r.source_url}
            </span>
          </a>
        ) : (
          <span className="text-fabric-gray-130 text-xs">—</span>
        ),
    },
  ];

  if (rc.isLoading) return <LoadingState />;
  if (rc.isError) return <ErrorState error={rc.error} onRetry={() => rc.refetch()} />;
  return (
    <DataTable
      data={rc.data ?? []}
      columns={columns}
      rowKey={(r) => r.name}
      initialSort={{ id: "name", dir: "asc" }}
    />
  );
}

// ---------- FOCUS export ----------
function FocusTab() {
  const info = useFocusExportInfo();
  return (
    <div className="flex flex-col gap-4 max-w-3xl">
      <div>
        <h2 className="text-base font-semibold text-fabric-gray-190">FOCUS 1.1 export</h2>
        <p className="text-sm text-fabric-gray-130 mt-1">
          Download a FinOps Open Cost &amp; Usage Specification (FOCUS)–compliant CSV
          containing every cost event in the ledger. Use this with FinOps Hubs,
          IBM Apptio, Spot.io, Vantage or any FOCUS-aware tool to consolidate
          AI spend with the rest of your cloud bill.
        </p>
      </div>
      {info.isLoading ? (
        <LoadingState />
      ) : info.isError ? (
        <ErrorState error={info.error} onRetry={() => info.refetch()} />
      ) : (
        <Card>
          <CardBody className="flex items-center justify-between gap-4">
            <div>
              <div className="text-xs uppercase tracking-wide text-fabric-gray-130 font-semibold">
                Format
              </div>
              <div className="text-sm font-medium text-fabric-gray-190 mt-0.5">
                {info.data?.format}
              </div>
              <div className="text-xs text-fabric-gray-130 mt-2 tabular-nums">
                {formatNumber(info.data?.row_count ?? 0)} rows · {info.data?.columns.length} columns
              </div>
            </div>
            <a
              href="/api/v1/reports/focus-export?download=true"
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-md bg-fabric-blue text-white text-sm font-medium hover:bg-fabric-blue-dark transition-colors"
            >
              <Download size={14} /> Download CSV
            </a>
          </CardBody>
        </Card>
      )}
      {info.data?.columns && (
        <Card>
          <CardHeader title="Columns included" />
          <CardBody>
            <div className="flex flex-wrap gap-2">
              {info.data.columns.map((c) => (
                <Badge key={c} tone="neutral" size="xs">
                  {c}
                </Badge>
              ))}
            </div>
          </CardBody>
        </Card>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="bg-fabric-gray-10 rounded-md p-3 border border-fabric-gray-20">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-fabric-gray-130">
        {label}
      </div>
      <div className="text-sm font-medium text-fabric-gray-190 mt-1 tabular-nums">
        {value}
      </div>
    </div>
  );
}
