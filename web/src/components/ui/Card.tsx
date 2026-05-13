import clsx from "clsx";
import type { HTMLAttributes, PropsWithChildren, ReactNode } from "react";

export function Card({
  className,
  children,
  ...rest
}: PropsWithChildren<HTMLAttributes<HTMLDivElement>>) {
  return (
    <div
      className={clsx(
        "bg-white border border-fabric-gray-30 rounded-md shadow-sm",
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  );
}

export interface CardHeaderProps {
  title: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  className?: string;
}

export function CardHeader({ title, subtitle, action, className }: CardHeaderProps) {
  return (
    <div
      className={clsx(
        "flex items-start justify-between gap-3 px-5 pt-4 pb-3 border-b border-fabric-gray-20",
        className,
      )}
    >
      <div className="min-w-0">
        <h3 className="text-sm font-semibold text-fabric-gray-190 leading-tight">
          {title}
        </h3>
        {subtitle && (
          <p className="text-xs text-fabric-gray-130 mt-0.5">{subtitle}</p>
        )}
      </div>
      {action && <div className="flex-shrink-0">{action}</div>}
    </div>
  );
}

export function CardBody({
  className,
  children,
}: PropsWithChildren<{ className?: string }>) {
  return <div className={clsx("p-5", className)}>{children}</div>;
}
