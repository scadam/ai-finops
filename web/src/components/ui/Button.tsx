import clsx from "clsx";
import type { ButtonHTMLAttributes, PropsWithChildren } from "react";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "subtle";
export type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}

const sizeMap: Record<ButtonSize, string> = {
  sm: "text-xs px-2.5 py-1.5 gap-1",
  md: "text-sm px-3.5 py-2 gap-1.5",
  lg: "text-sm px-5 py-2.5 gap-2",
};

const variants: Record<ButtonVariant, string> = {
  primary:
    "bg-fabric-blue text-white border border-fabric-blue hover:bg-fabric-blue-dark hover:border-fabric-blue-dark",
  secondary:
    "bg-white text-fabric-gray-190 border border-fabric-gray-30 hover:bg-fabric-gray-10",
  subtle:
    "bg-fabric-gray-20 text-fabric-gray-190 border border-transparent hover:bg-fabric-gray-30",
  ghost:
    "bg-transparent text-fabric-gray-160 border border-transparent hover:bg-fabric-gray-20",
  danger:
    "bg-fabric-error text-white border border-fabric-error hover:bg-red-700 hover:border-red-700",
};

export function Button({
  variant = "secondary",
  size = "md",
  loading,
  className,
  disabled,
  children,
  ...rest
}: PropsWithChildren<ButtonProps>) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={clsx(
        "inline-flex items-center justify-center font-medium rounded-md transition-colors",
        "disabled:opacity-50 disabled:cursor-not-allowed",
        sizeMap[size],
        variants[variant],
        className,
      )}
    >
      {loading && (
        <span className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />
      )}
      {children}
    </button>
  );
}
