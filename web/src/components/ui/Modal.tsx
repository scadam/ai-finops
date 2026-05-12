import clsx from "clsx";
import { X } from "lucide-react";
import {
  type PropsWithChildren,
  type ReactNode,
  useEffect,
} from "react";

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  description?: ReactNode;
  size?: "sm" | "md" | "lg";
  footer?: ReactNode;
}

const sizeMap = { sm: "max-w-sm", md: "max-w-md", lg: "max-w-2xl" };

export function Modal({
  open,
  onClose,
  title,
  description,
  size = "md",
  footer,
  children,
}: PropsWithChildren<ModalProps>) {
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

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-black/30 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden
      />
      <div
        role="dialog"
        aria-modal="true"
        className={clsx(
          "relative w-full bg-white rounded-lg shadow-xl border border-fabric-gray-30 flex flex-col max-h-[85vh]",
          sizeMap[size],
        )}
      >
        <div className="flex items-start justify-between gap-3 px-5 pt-4 pb-3 border-b border-fabric-gray-20">
          <div className="min-w-0">
            {title && (
              <h2 className="text-base font-semibold text-fabric-gray-190">{title}</h2>
            )}
            {description && (
              <p className="text-xs text-fabric-gray-130 mt-1">{description}</p>
            )}
          </div>
          <button
            onClick={onClose}
            aria-label="Close dialog"
            className="rounded-md p-1 text-fabric-gray-130 hover:bg-fabric-gray-20 hover:text-fabric-gray-190 transition-colors"
          >
            <X size={16} />
          </button>
        </div>
        <div className="px-5 py-4 overflow-auto flex-1">{children}</div>
        {footer && (
          <div className="px-5 py-3 border-t border-fabric-gray-20 bg-fabric-gray-10 flex items-center justify-end gap-2 rounded-b-lg">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
