import clsx from "clsx";
import { X } from "lucide-react";
import { type PropsWithChildren, type ReactNode, useEffect } from "react";

export interface SlideOverProps {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  subtitle?: ReactNode;
  width?: "md" | "lg" | "xl";
  footer?: ReactNode;
}

const widthMap = { md: "max-w-md", lg: "max-w-xl", xl: "max-w-3xl" };

export function SlideOver({
  open,
  onClose,
  title,
  subtitle,
  width = "lg",
  footer,
  children,
}: PropsWithChildren<SlideOverProps>) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  return (
    <div
      className={clsx(
        "fixed inset-0 z-50 transition-opacity",
        open ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none",
      )}
      aria-hidden={!open}
    >
      <div
        className="absolute inset-0 bg-black/30 backdrop-blur-sm"
        onClick={onClose}
      />
      <aside
        role="dialog"
        aria-modal="true"
        className={clsx(
          "absolute right-0 top-0 h-full w-full bg-white shadow-2xl border-l border-fabric-gray-30 flex flex-col transform transition-transform duration-200",
          widthMap[width],
          open ? "translate-x-0" : "translate-x-full",
        )}
      >
        <header className="flex items-start justify-between gap-3 px-6 pt-5 pb-4 border-b border-fabric-gray-20">
          <div className="min-w-0">
            {title && (
              <h2 className="text-lg font-semibold text-fabric-gray-190 truncate">
                {title}
              </h2>
            )}
            {subtitle && (
              <p className="text-sm text-fabric-gray-130 mt-0.5">{subtitle}</p>
            )}
          </div>
          <button
            onClick={onClose}
            aria-label="Close panel"
            className="rounded-md p-1.5 text-fabric-gray-130 hover:bg-fabric-gray-20 hover:text-fabric-gray-190 transition-colors"
          >
            <X size={18} />
          </button>
        </header>
        <div className="flex-1 overflow-auto px-6 py-5">{children}</div>
        {footer && (
          <footer className="px-6 py-3 border-t border-fabric-gray-20 bg-fabric-gray-10 flex items-center justify-end gap-2">
            {footer}
          </footer>
        )}
      </aside>
    </div>
  );
}
