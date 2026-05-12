import { Check, Filter, X } from "lucide-react";
import { useMemo, useState } from "react";
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
  Modal,
  ProgressBar,
  Select,
  Textarea,
  effortTone,
} from "@/components/ui";
import { useDismissOptimisation, useOptimisations } from "@/hooks";
import type { Optimisation } from "@/types/api";
import { formatCurrency, titleCase, toNum } from "@/utils/format";

const CATEGORY_OPTIONS = [
  { value: "", label: "All categories" },
  { value: "license_right_sizing", label: "License right-sizing" },
  { value: "pack_vs_payg", label: "Pack vs. PAYG" },
  { value: "model_downshift", label: "Model downshift" },
  { value: "prompt_caching", label: "Prompt caching" },
  { value: "batch_api", label: "Batch API" },
  { value: "agent_technology_switch", label: "Agent consolidation" },
  { value: "license_channel_routing", label: "License/channel routing" },
  { value: "zombie_ft_model", label: "Fine-tuning lifecycle" },
  { value: "ai_search_rightsizing", label: "AI Search rightsizing" },
  { value: "idle_endpoint", label: "Idle resource" },
  { value: "graph_grounding_toggle", label: "Graph grounding toggle" },
  { value: "classic_answer_fallback", label: "Classic answer fallback" },
  { value: "ptu_reservation", label: "PTU reservation" },
];

const EFFORT_OPTIONS = [
  { value: "", label: "Any effort" },
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
];

const SORT_OPTIONS = [
  { value: "saving_desc", label: "Saving · highest first" },
  { value: "confidence_desc", label: "Confidence · highest first" },
  { value: "effort_asc", label: "Effort · lowest first" },
];

const EFFORT_RANK: Record<string, number> = { low: 1, medium: 2, high: 3 };

export default function Optimisations() {
  const [category, setCategory] = useState("");
  const [effort, setEffort] = useState("");
  const [minSaving, setMinSaving] = useState(0);
  const [sort, setSort] = useState("saving_desc");
  const [dismissTarget, setDismissTarget] = useState<Optimisation | null>(null);
  const [reason, setReason] = useState("");

  const opts = useOptimisations({
    category: category || undefined,
    effort: effort || undefined,
    min_saving: minSaving > 0 ? minSaving : undefined,
  });
  const dismissOpt = useDismissOptimisation();

  const sorted = useMemo(() => {
    const list = [...(opts.data ?? [])];
    list.sort((a, b) => {
      switch (sort) {
        case "confidence_desc":
          return (b.confidence ?? 0) - (a.confidence ?? 0);
        case "effort_asc":
          return (
            (EFFORT_RANK[a.implementation_effort] ?? 4) -
            (EFFORT_RANK[b.implementation_effort] ?? 4)
          );
        case "saving_desc":
        default:
          return toNum(b.monthly_saving_usd) - toNum(a.monthly_saving_usd);
      }
    });
    return list;
  }, [opts.data, sort]);

  const totalSaving = sorted.reduce(
    (s, o) => s + toNum(o.monthly_saving_usd),
    0,
  );

  function confirmDismiss() {
    if (!dismissTarget) return;
    dismissOpt.mutate(
      { id: dismissTarget.id, reason },
      {
        onSettled: () => {
          setDismissTarget(null);
          setReason("");
        },
      },
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <Card>
        <CardHeader
          title="Filters"
          subtitle={
            <span>
              Showing <strong>{sorted.length}</strong> recommendations · total potential{" "}
              <strong>{formatCurrency(totalSaving, { decimals: 0 })}</strong>/mo
            </span>
          }
          action={<Filter size={16} className="text-fabric-gray-130" />}
        />
        <CardBody className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Field label="Category">
            <Select
              options={CATEGORY_OPTIONS}
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            />
          </Field>
          <Field label="Effort">
            <Select
              options={EFFORT_OPTIONS}
              value={effort}
              onChange={(e) => setEffort(e.target.value)}
            />
          </Field>
          <Field label={`Min monthly saving · ${formatCurrency(minSaving, { decimals: 0 })}`}>
            <input
              type="range"
              min={0}
              max={5000}
              step={50}
              value={minSaving}
              onChange={(e) => setMinSaving(Number(e.target.value))}
              className="w-full accent-fabric-blue"
              aria-label="Minimum monthly saving"
            />
          </Field>
          <Field label="Sort by">
            <Select
              options={SORT_OPTIONS}
              value={sort}
              onChange={(e) => setSort(e.target.value)}
            />
          </Field>
        </CardBody>
      </Card>

      {opts.isLoading ? (
        <LoadingState message="Loading recommendations…" />
      ) : opts.isError ? (
        <ErrorState error={opts.error} onRetry={() => opts.refetch()} />
      ) : sorted.length === 0 ? (
        <Card>
          <EmptyState
            title="No matching recommendations"
            message="Try widening filters or lowering the minimum saving threshold."
          />
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {sorted.map((o, idx) => {
            const before = toNum(o.before_cost_usd);
            const after = toNum(o.after_cost_usd);
            const confidencePct = Math.round((o.confidence ?? 0) * 100);
            return (
              <Card key={o.id} className="flex flex-col">
                <CardBody className="flex-1 flex flex-col gap-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-semibold uppercase tracking-wide text-fabric-gray-130">
                        Rank
                      </span>
                      <span className="inline-flex items-center justify-center w-6 h-6 rounded-md bg-fabric-blue text-white text-xs font-semibold">
                        {idx + 1}
                      </span>
                    </div>
                    <Badge tone={effortTone(o.implementation_effort)}>
                      {titleCase(String(o.implementation_effort))} effort
                    </Badge>
                  </div>
                  <div>
                    <Badge tone="blue" size="xs" className="mb-2">
                      {titleCase(String(o.category))}
                    </Badge>
                    <h3 className="text-sm font-semibold text-fabric-gray-190 leading-snug">
                      {o.title}
                    </h3>
                  </div>
                  <p className="text-xs text-fabric-gray-130 line-clamp-3">
                    {o.description}
                  </p>
                  {o.evidence && (
                    <p className="text-[11px] text-fabric-gray-130 italic border-l-2 border-fabric-gray-30 pl-2">
                      {o.evidence}
                    </p>
                  )}
                  <div className="flex items-center gap-2 text-xs">
                    <span className="text-fabric-gray-130 line-through tabular-nums">
                      {formatCurrency(before, { decimals: 0 })}
                    </span>
                    <span className="text-fabric-gray-130">→</span>
                    <span className="text-fabric-gray-190 font-medium tabular-nums">
                      {formatCurrency(after, { decimals: 0 })}
                    </span>
                  </div>
                  <div className="mt-auto pt-2">
                    <div className="text-2xl font-semibold text-fabric-success tabular-nums">
                      {formatCurrency(o.monthly_saving_usd, { decimals: 0 })}
                      <span className="text-xs font-normal text-fabric-gray-130 ml-1">
                        / month
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-[11px] text-fabric-gray-130 mt-2 mb-1">
                      <span>Confidence</span>
                      <span className="tabular-nums">{confidencePct}%</span>
                    </div>
                    <ProgressBar value={confidencePct} tone="blue" />
                  </div>
                </CardBody>
                <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-fabric-gray-20 bg-fabric-gray-10 rounded-b-md">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setDismissTarget(o)}
                  >
                    <X size={12} /> Dismiss
                  </Button>
                  <Button variant="primary" size="sm">
                    <Check size={12} /> Accept
                  </Button>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      <Modal
        open={!!dismissTarget}
        onClose={() => setDismissTarget(null)}
        title="Dismiss recommendation"
        description={dismissTarget?.title}
        footer={
          <>
            <Button variant="ghost" onClick={() => setDismissTarget(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={dismissOpt.isPending}
              onClick={confirmDismiss}
            >
              Dismiss
            </Button>
          </>
        }
      >
        <Field
          label="Reason for dismissal"
          hint="Captured for audit and shown in the optimisation history."
        >
          <Textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. Already mitigated through reserved capacity"
          />
        </Field>
        <Field label="Optional reference" className="mt-3">
          <Input placeholder="ticket ID, change record…" />
        </Field>
      </Modal>
    </div>
  );
}
