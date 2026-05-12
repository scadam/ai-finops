import clsx from "clsx";
import type {
  InputHTMLAttributes,
  LabelHTMLAttributes,
  PropsWithChildren,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";

const baseField =
  "w-full bg-white border border-fabric-gray-30 rounded-md px-3 py-2 text-sm text-fabric-gray-190 " +
  "placeholder:text-fabric-gray-130 hover:border-fabric-gray-130 focus:border-fabric-blue " +
  "focus:outline-none focus:ring-2 focus:ring-fabric-blue/20 transition-colors disabled:bg-fabric-gray-10 disabled:text-fabric-gray-130";

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...rest} className={clsx(baseField, className)} />;
}

export function Textarea({
  className,
  ...rest
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...rest} className={clsx(baseField, "resize-y min-h-[72px]", className)} />;
}

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps
  extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "children"> {
  options: SelectOption[];
  placeholder?: string;
}

export function Select({
  options,
  placeholder,
  className,
  value,
  ...rest
}: SelectProps) {
  return (
    <select
      {...rest}
      value={value ?? ""}
      className={clsx(baseField, "appearance-none pr-8 bg-no-repeat", className)}
      style={{
        backgroundImage:
          "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 20 20' fill='%23605e5c'><path d='M5.5 7.5l4.5 4.5 4.5-4.5'/></svg>\")",
        backgroundPosition: "right 8px center",
        backgroundSize: "16px",
      }}
    >
      {placeholder !== undefined && <option value="">{placeholder}</option>}
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

export function Label({
  className,
  children,
  ...rest
}: PropsWithChildren<LabelHTMLAttributes<HTMLLabelElement>>) {
  return (
    <label
      {...rest}
      className={clsx(
        "block text-xs font-semibold text-fabric-gray-160 mb-1",
        className,
      )}
    >
      {children}
    </label>
  );
}

export function Field({
  label,
  hint,
  children,
  className,
}: PropsWithChildren<{ label?: string; hint?: string; className?: string }>) {
  return (
    <div className={clsx("flex flex-col", className)}>
      {label && <Label>{label}</Label>}
      {children}
      {hint && <p className="text-[11px] text-fabric-gray-130 mt-1">{hint}</p>}
    </div>
  );
}
