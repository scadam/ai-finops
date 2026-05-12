import clsx from "clsx";
import { ArrowDown, ArrowUp, Minus } from "lucide-react";
import type { ReactNode } from "react";
import { Card } from "./Card";

export interface KPICardProps {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  trend?: number | null;
  trendLabel?: string;
  invertTrend?: boolean;
  icon?: ReactNode;
  accent?: "blue" | "success" | "warning" | "error";
}

const accentMap = {
  blue: "bg-fabric-blue-light text-fabric-blue-dark",
  success: "bg-emerald-50 text-fabric-success",
  warning: "bg-amber-50 text-amber-700",
  error: "bg-red-50 text-fabric-error",
};

export function KPICard({
  label,
  value,
  sub,
  trend,
  trendLabel,
  invertTrend,
  icon,
  accent = "blue",
}: KPICardProps) {
  const hasTrend = trend !== null && trend !== undefined && Number.isFinite(trend);
  const positive = (trend ?? 0) > 0;
  const negative = (trend ?? 0) < 0;
  const good = invertTrend ? negative : positive;
  const bad = invertTrend ? positive : negative;
  const trendColor = good
    ? "text-fabric-success"
    : bad
      ? "text-fabric-error"
      : "text-fabric-gray-130";
  const TrendIcon = positive ? ArrowUp : negative ? ArrowDown : Minus;

  return (
    <Card className="p-5 flex flex-col gap-3 hover:shadow-card transition-shadow">
      <div className="flex items-start justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-fabric-gray-130">
          {label}
        </span>
        {icon && (
          <span
            className={clsx(
              "rounded-md p-1.5 inline-flex items-center justify-center",
              accentMap[accent],
            )}
          >
            {icon}
          </span>
        )}
      </div>
      <div className="text-3xl font-semibold text-fabric-gray-190 tabular-nums leading-none">
        {value}
      </div>
      <div className="flex items-center justify-between text-xs text-fabric-gray-130 min-h-[1.25rem]">
        <span className="truncate">{sub}</span>
        {hasTrend && (
          <span
            className={clsx(
              "inline-flex items-center gap-0.5 font-medium tabular-nums",
              trendColor,
            )}
          >
            <TrendIcon size={12} />
            {Math.abs(trend ?? 0).toFixed(1)}% {trendLabel ?? ""}
          </span>
        )}
      </div>
    </Card>
  );
}
