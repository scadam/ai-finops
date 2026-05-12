import clsx from "clsx";
import {
  AlertTriangle,
  BarChart3,
  Bot,
  CalendarDays,
  ChevronDown,
  Lightbulb,
  ShieldCheck,
  Sliders,
  Sparkles,
} from "lucide-react";
import { type ReactNode, useMemo } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { Badge, statusTone } from "@/components/ui";
import { useAnomalies, useOptimisations, useRateCardStatus } from "@/hooks";

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
  end?: boolean;
  badge?: ReactNode;
}

const TITLES: Record<string, string> = {
  "/": "Dashboard",
  "/agents": "Agent Explorer",
  "/modeler": "What-If Modeler",
  "/optimisations": "Optimisations",
  "/governance": "Governance",
};

export function Layout() {
  const location = useLocation();
  const optimisations = useOptimisations();
  const anomalies = useAnomalies({ acknowledged: false });
  const rateCards = useRateCardStatus();

  const optCount = optimisations.data?.length ?? 0;
  const anomalyCount = anomalies.data?.length ?? 0;
  const rateCardStale =
    rateCards.data?.some((c) => c.is_stale) ?? false;

  const nav: NavItem[] = useMemo(
    () => [
      { to: "/", label: "Dashboard", icon: <BarChart3 size={16} />, end: true },
      { to: "/agents", label: "Agent Explorer", icon: <Bot size={16} /> },
      { to: "/modeler", label: "What-If Modeler", icon: <Sliders size={16} /> },
      {
        to: "/optimisations",
        label: "Optimisations",
        icon: <Lightbulb size={16} />,
        badge: optCount > 0 ? (
          <Badge tone="blue" size="xs">{optCount}</Badge>
        ) : null,
      },
      {
        to: "/governance",
        label: "Governance",
        icon: <ShieldCheck size={16} />,
        badge: anomalyCount > 0 ? (
          <Badge tone="error" size="xs" dot>{anomalyCount}</Badge>
        ) : null,
      },
    ],
    [optCount, anomalyCount],
  );

  const title = TITLES[location.pathname] ?? "AI FinOps";

  return (
    <div className="flex min-h-screen bg-fabric-gray-10 text-fabric-gray-190">
      {/* Sidebar */}
      <aside className="w-60 flex-shrink-0 bg-white border-r border-fabric-gray-30 flex flex-col">
        <div className="px-5 pt-5 pb-4 border-b border-fabric-gray-20">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-md bg-fabric-blue text-white flex items-center justify-center shadow-sm">
              <Sparkles size={16} />
            </div>
            <div className="leading-tight">
              <div className="text-sm font-semibold text-fabric-gray-190">AI FinOps</div>
              <div className="text-[10px] uppercase tracking-wide text-fabric-gray-130">
                Frontier Platform
              </div>
            </div>
          </div>
        </div>

        <nav className="flex-1 px-3 py-4 flex flex-col gap-0.5">
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-2.5 px-3 py-2 text-sm rounded-md transition-colors",
                  isActive
                    ? "bg-fabric-blue-light text-fabric-blue-dark font-semibold"
                    : "text-fabric-gray-160 hover:bg-fabric-gray-20",
                )
              }
            >
              {item.icon}
              <span className="flex-1">{item.label}</span>
              {item.badge}
            </NavLink>
          ))}
        </nav>

        <div className="px-4 pb-5 pt-3 border-t border-fabric-gray-20 flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <Badge tone="success" dot>env: prod</Badge>
          </div>
          <div className="text-[11px] text-fabric-gray-130 leading-tight">
            <div className="font-semibold text-fabric-gray-160">Contoso Ltd</div>
            <div>tenant · contoso.onmicrosoft.com</div>
          </div>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="sticky top-0 z-20 bg-white/85 backdrop-blur border-b border-fabric-gray-30 px-6 py-3 flex items-center justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-lg font-semibold text-fabric-gray-190 truncate">
              {title}
            </h1>
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1.5 rounded-md border border-fabric-gray-30 hover:bg-fabric-gray-20 text-fabric-gray-160"
            >
              <CalendarDays size={14} />
              May 2026
              <ChevronDown size={12} />
            </button>
            <Badge
              tone={statusTone(rateCardStale ? "stale" : "fresh")}
              dot
              className="text-xs"
            >
              {rateCards.isLoading
                ? "Rate cards · loading"
                : rateCardStale
                  ? "Rate cards · stale"
                  : "Rate cards · fresh"}
            </Badge>
            {anomalyCount > 0 && (
              <Badge tone="warning" className="text-xs">
                <AlertTriangle size={12} className="mr-1" />
                {anomalyCount} open anomalies
              </Badge>
            )}
            <div
              className="w-8 h-8 rounded-full bg-fabric-blue text-white text-xs font-semibold flex items-center justify-center"
              aria-label="User avatar"
              title="Alex Chen · CFO Office"
            >
              AC
            </div>
          </div>
        </header>

        <main className="flex-1 px-6 py-6 overflow-x-hidden">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
