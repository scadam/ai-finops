import clsx from "clsx";
import type { PropsWithChildren } from "react";

export type BadgeTone =
  | "neutral"
  | "blue"
  | "success"
  | "warning"
  | "error"
  | "purple";

const tones: Record<BadgeTone, string> = {
  neutral: "bg-fabric-gray-20 text-fabric-gray-160 border-fabric-gray-30",
  blue: "bg-fabric-blue-light text-fabric-blue-dark border-fabric-blue-light",
  success: "bg-emerald-50 text-fabric-success border-emerald-100",
  warning: "bg-amber-50 text-amber-700 border-amber-100",
  error: "bg-red-50 text-fabric-error border-red-100",
  purple: "bg-purple-50 text-purple-700 border-purple-100",
};

export interface BadgeProps {
  tone?: BadgeTone;
  className?: string;
  size?: "xs" | "sm";
  dot?: boolean;
}

export function Badge({
  tone = "neutral",
  size = "sm",
  className,
  dot,
  children,
}: PropsWithChildren<BadgeProps>) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 font-medium border rounded-full",
        size === "xs" ? "text-[10px] px-1.5 py-px" : "text-xs px-2 py-0.5",
        tones[tone],
        className,
      )}
    >
      {dot && (
        <span
          className={clsx(
            "inline-block rounded-full",
            size === "xs" ? "w-1.5 h-1.5" : "w-2 h-2",
            tone === "neutral" && "bg-fabric-gray-130",
            tone === "blue" && "bg-fabric-blue",
            tone === "success" && "bg-fabric-success",
            tone === "warning" && "bg-fabric-warning",
            tone === "error" && "bg-fabric-error",
            tone === "purple" && "bg-purple-500",
          )}
        />
      )}
      {children}
    </span>
  );
}

export function severityTone(severity: string | null | undefined): BadgeTone {
  switch ((severity ?? "").toLowerCase()) {
    case "critical":
      return "error";
    case "high":
      return "error";
    case "medium":
      return "warning";
    case "low":
      return "blue";
    default:
      return "neutral";
  }
}

export function effortTone(effort: string | null | undefined): BadgeTone {
  switch ((effort ?? "").toLowerCase()) {
    case "low":
      return "success";
    case "medium":
      return "warning";
    case "high":
      return "error";
    default:
      return "neutral";
  }
}

export function statusTone(status: string | null | undefined): BadgeTone {
  switch ((status ?? "").toLowerCase()) {
    case "on_track":
    case "production":
    case "ok":
    case "active":
    case "fresh":
      return "success";
    case "warning":
    case "stale":
      return "warning";
    case "exceeded":
    case "error":
    case "failed":
      return "error";
    default:
      return "neutral";
  }
}
