import clsx from "clsx";

export interface ProgressBarProps {
  value: number; // 0-100
  tone?: "blue" | "success" | "warning" | "error";
  className?: string;
  showLabel?: boolean;
}

const tones = {
  blue: "bg-fabric-blue",
  success: "bg-fabric-success",
  warning: "bg-fabric-warning",
  error: "bg-fabric-error",
};

export function ProgressBar({
  value,
  tone = "blue",
  className,
  showLabel,
}: ProgressBarProps) {
  const v = Math.max(0, Math.min(100, Number.isFinite(value) ? value : 0));
  return (
    <div className={clsx("w-full", className)}>
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1.5 rounded-full bg-fabric-gray-20 overflow-hidden">
          <div
            className={clsx("h-full rounded-full transition-all", tones[tone])}
            style={{ width: `${v}%` }}
          />
        </div>
        {showLabel && (
          <span className="text-xs text-fabric-gray-130 tabular-nums w-10 text-right">
            {v.toFixed(0)}%
          </span>
        )}
      </div>
    </div>
  );
}
