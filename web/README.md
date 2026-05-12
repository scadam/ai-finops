# AI FinOps · Web

Production React frontend for the AI FinOps platform.

## Stack

- Vite 5 + React 18 + TypeScript (strict)
- Tailwind 3 with Microsoft Fabric design tokens
- Tanstack Query v5 · React Router v6
- Recharts · lucide-react · axios · clsx

## Pages

| Route | Description |
| --- | --- |
| `/` | Dashboard — KPIs, spend trend, top agents, anomalies, optimisations |
| `/agents` | Agent Explorer — sortable table + slide-over detail |
| `/whatif` | What-If Modeler — 3-step scenario wizard with live estimate + comparison |
| `/optimisations` | Recommendation backlog with dismiss flow |
| `/governance` | Budgets · Anomalies · Licenses · Rate cards · FOCUS export |

## Develop

```bash
cd web
npm install
npm run dev     # starts on http://127.0.0.1:5173 (proxies /api -> 127.0.0.1:8000)
```

The backend FastAPI server must be running on `127.0.0.1:8000` (see repo root README).

## Build

```bash
npm run build   # outputs dist/
npm run preview # serves dist/ on http://127.0.0.1:4173
```

Both `dev` and `preview` proxy `/api/*` to the FastAPI backend on port 8000.

## Notes

- All money values arrive as `Decimal`-preserving strings — use the `toNum()` helper before arithmetic.
- Path alias `@/*` maps to `src/*`.
- Query defaults: 30s stale time, 5m gc time, no refetch on focus.
