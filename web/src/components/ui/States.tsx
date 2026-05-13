import { AlertCircle, Inbox, Loader2 } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "./Button";

export function LoadingState({ message = "Loading…" }: { message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-fabric-gray-130">
      <Loader2 size={28} className="animate-spin text-fabric-blue mb-3" />
      <p className="text-sm">{message}</p>
    </div>
  );
}

export interface ErrorStateProps {
  title?: string;
  message?: string;
  error?: unknown;
  onRetry?: () => void;
}

export function ErrorState({
  title = "Something went wrong",
  message,
  error,
  onRetry,
}: ErrorStateProps) {
  const detail =
    message ??
    (error instanceof Error
      ? error.message
      : typeof error === "string"
        ? error
        : "Unable to load data. Please try again.");
  return (
    <div className="flex flex-col items-center justify-center py-10 px-4 text-center">
      <div className="rounded-full bg-red-50 p-2.5 mb-3">
        <AlertCircle size={22} className="text-fabric-error" />
      </div>
      <h3 className="text-sm font-semibold text-fabric-gray-190">{title}</h3>
      <p className="text-xs text-fabric-gray-130 mt-1 max-w-md">{detail}</p>
      {onRetry && (
        <Button onClick={onRetry} variant="secondary" size="sm" className="mt-4">
          Retry
        </Button>
      )}
    </div>
  );
}

export interface EmptyStateProps {
  title?: string;
  message?: string;
  icon?: ReactNode;
  action?: ReactNode;
}

export function EmptyState({
  title = "Nothing here yet",
  message,
  icon,
  action,
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      <div className="rounded-full bg-fabric-gray-20 p-3 mb-3 text-fabric-gray-130">
        {icon ?? <Inbox size={22} />}
      </div>
      <h3 className="text-sm font-semibold text-fabric-gray-190">{title}</h3>
      {message && (
        <p className="text-xs text-fabric-gray-130 mt-1 max-w-md">{message}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
