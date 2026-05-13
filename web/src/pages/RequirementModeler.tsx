import { useState } from "react";
import { Sparkles, Wand2 } from "lucide-react";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  Field,
  Input,
  Select,
} from "@/components/ui";
import { apiClient } from "@/api/client";
import { formatCurrency } from "@/utils/format";

// =====================================================================
// Requirement-driven modeller (Part 2 of the AI FinOps roadmap).
// Talks to /api/v1/modeler/{requirements,seed,refine,promote}.
// =====================================================================

const MAX_ALTERNATIVES = 5;

type SeededAxis = {
  value: string | number | boolean;
  locked: boolean;
  source: string;
  rationale_id: string | null;
};

type SeedResponse = {
  session_id: string;
  requirement_id: string;
  rationale_id: string | null;
  rationale: { id?: string; source?: string; text?: string };
  notes: string[];
  available_channels: string[];
  axes: Record<string, SeededAxis>;
  profile: Record<string, unknown>;
  score: {
    fit: number;
    cost_efficiency: number;
    risk: number;
    compliance: number;
    total: number;
    monthly_usd: string;
    rationale: string[];
  };
  alternatives: Array<{
    agent_type: string;
    channel: string;
    score: { total: number; monthly_usd: string };
  }>;
};

export default function RequirementModeler() {
  const [description, setDescription] = useState(
    "Tier-1 helpdesk for 4000 employees, must cite SharePoint policies, no external chat. Confidential data."
  );
  const [seed, setSeed] = useState<SeedResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [agentName, setAgentName] = useState("Tier-1 Helpdesk");
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const req = await apiClient.post("/modeler/requirements", {
        description,
      });
      const seeded = await apiClient.post<SeedResponse>("/modeler/seed", {
        requirement_id: req.data.id,
      });
      setSeed(seeded.data);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? e.message ?? "request failed");
    } finally {
      setBusy(false);
    }
  };

  const refine = async (axis: string, value: string) => {
    if (!seed) return;
    setBusy(true);
    try {
      const r = await apiClient.post("/modeler/refine", {
        session_id: seed.session_id,
        edits: { [axis]: value },
      });
      setSeed({
        ...seed,
        profile: r.data.profile,
        score: { ...seed.score, ...r.data.score },
      });
    } finally {
      setBusy(false);
    }
  };

  const promote = async () => {
    if (!seed) return;
    setBusy(true);
    try {
      await apiClient.post("/modeler/promote", {
        session_id: seed.session_id,
        agent_name: agentName,
      });
      alert("Promoted to Agent Explorer.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6 p-6">
      <header className="flex items-center gap-3">
        <Wand2 className="text-indigo-500" />
        <div>
          <h1 className="text-xl font-semibold">Agent Modeller</h1>
          <p className="text-sm text-gray-500">
            Describe the business requirement; we seed an evidence-based
            agent design with every axis editable.
          </p>
        </div>
      </header>

      <Card>
        <CardHeader title="Step 0 — Requirement" />
        <CardBody className="space-y-3">
          <Field label="Plain-English description">
            <textarea
              className="w-full rounded border border-gray-300 p-2 text-sm"
              rows={4}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </Field>
          <Button onClick={run} disabled={busy}>
            <Sparkles size={14} className="mr-1" />
            Seed design
          </Button>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </CardBody>
      </Card>

      {seed && (
        <>
          <Card>
            <CardHeader
              title="Step 1 — Seeded design"
              action={seed.rationale_id ? <Badge tone="blue">{seed.rationale_id}</Badge> : null}
            />
            <CardBody className="space-y-2 text-sm">
              {seed.rationale?.text && (
                <p className="rounded bg-blue-50 p-3 text-blue-900">
                  <strong>Why:</strong> {seed.rationale.text}
                  <br />
                  <em>Source: {seed.rationale.source}</em>
                </p>
              )}
              {seed.notes.length > 0 && (
                <ul className="list-disc pl-5 text-amber-700">
                  {seed.notes.map((n) => (
                    <li key={n}>{n}</li>
                  ))}
                </ul>
              )}
              <dl className="grid grid-cols-2 gap-2">
                {Object.entries(seed.axes).map(([k, v]) => (
                  <div key={k} className="rounded border border-gray-200 p-2">
                    <dt className="text-xs uppercase text-gray-500">{k}</dt>
                    <dd className="font-mono text-sm">{String(v.value)}</dd>
                    <small className="text-gray-400">
                      source: {v.source}
                      {v.rationale_id ? ` · ${v.rationale_id}` : ""}
                    </small>
                  </div>
                ))}
              </dl>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Step 2 — Edit any axis (live re-pricing)" />
            <CardBody className="grid grid-cols-2 gap-3">
              <Field label="Channel">
                <Select
                  value={String(seed.profile.channel)}
                  onChange={(e) => refine("channel", e.target.value)}
                  options={seed.available_channels.map((c) => ({
                    value: c,
                    label: c,
                  }))}
                />
              </Field>
              <Field label="Agent type">
                <Select
                  value={String(seed.profile.agent_type)}
                  onChange={(e) => refine("agent_type", e.target.value)}
                  options={[
                    "declarative_instruction",
                    "declarative_public",
                    "declarative_tenant",
                    "copilot_studio_custom",
                    "foundry_native",
                    "foundry_hosted",
                    "hybrid_studio_foundry",
                  ].map((c) => ({ value: c, label: c }))}
                />
              </Field>
              <div className="col-span-2 grid grid-cols-4 gap-2 text-center text-sm">
                <Stat label="fit" value={seed.score.fit} />
                <Stat label="cost eff" value={seed.score.cost_efficiency} />
                <Stat label="risk" value={seed.score.risk} />
                <Stat label="compliance" value={seed.score.compliance} />
                <Stat label="total" value={seed.score.total} highlight />
                <Stat
                  label="$/month"
                  value={formatCurrency(Number(seed.score.monthly_usd))}
                  highlight
                />
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title={`Alternatives (top ${Math.min(MAX_ALTERNATIVES, seed.alternatives.length)})`} />
            <CardBody>
              <table className="w-full text-sm">
                <thead className="text-left text-xs uppercase text-gray-500">
                  <tr>
                    <th>Agent type</th>
                    <th>Channel</th>
                    <th>Total score</th>
                    <th>$/month</th>
                  </tr>
                </thead>
                <tbody>
                  {seed.alternatives.slice(0, MAX_ALTERNATIVES).map((a, i) => (
                    <tr key={`${a.agent_type}-${a.channel}-${i}`}>
                      <td>{a.agent_type}</td>
                      <td>{a.channel}</td>
                      <td>{a.score.total.toFixed(3)}</td>
                      <td>{formatCurrency(Number(a.score.monthly_usd))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Step 3 — Promote to Agent Explorer" />
            <CardBody className="flex items-end gap-3">
              <Field label="Agent name">
                <Input
                  value={agentName}
                  onChange={(e) => setAgentName(e.target.value)}
                />
              </Field>
              <Button onClick={promote} disabled={busy || !agentName}>
                Promote
              </Button>
            </CardBody>
          </Card>
        </>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  highlight,
}: {
  label: string;
  value: number | string;
  highlight?: boolean;
}) {
  return (
    <div
      className={`rounded p-2 ${
        highlight ? "bg-indigo-50 font-semibold" : "bg-gray-50"
      }`}
    >
      <div className="text-xs uppercase text-gray-500">{label}</div>
      <div>{typeof value === "number" ? value.toFixed(2) : value}</div>
    </div>
  );
}
