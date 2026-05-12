import clsx from "clsx";
import type { ReactNode } from "react";

export interface TabItem {
  id: string;
  label: ReactNode;
  badge?: ReactNode;
}

export interface TabsProps {
  tabs: TabItem[];
  active: string;
  onChange: (id: string) => void;
  className?: string;
}

export function Tabs({ tabs, active, onChange, className }: TabsProps) {
  return (
    <div className={clsx("border-b border-fabric-gray-30", className)}>
      <nav className="-mb-px flex gap-2 overflow-x-auto">
        {tabs.map((t) => {
          const isActive = t.id === active;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => onChange(t.id)}
              className={clsx(
                "px-4 py-2.5 text-sm font-medium border-b-2 -mb-px whitespace-nowrap inline-flex items-center gap-2 transition-colors",
                isActive
                  ? "border-fabric-blue text-fabric-blue"
                  : "border-transparent text-fabric-gray-130 hover:text-fabric-gray-190 hover:border-fabric-gray-30",
              )}
            >
              {t.label}
              {t.badge != null && <span className="text-xs">{t.badge}</span>}
            </button>
          );
        })}
      </nav>
    </div>
  );
}
