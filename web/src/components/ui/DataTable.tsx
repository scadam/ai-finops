import clsx from "clsx";
import { ChevronDown, ChevronUp, ChevronsUpDown, Search } from "lucide-react";
import { type ReactNode, useMemo, useState } from "react";
import { Input } from "./Input";
import { EmptyState } from "./States";

export interface DataTableColumn<T> {
  id: string;
  header: ReactNode;
  accessor: (row: T) => unknown;
  cell?: (row: T) => ReactNode;
  className?: string;
  align?: "left" | "right" | "center";
  sortable?: boolean;
  width?: string;
}

export interface DataTableProps<T> {
  data: T[];
  columns: DataTableColumn<T>[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  searchable?: boolean;
  searchPlaceholder?: string;
  initialSort?: { id: string; dir: "asc" | "desc" };
  emptyMessage?: string;
  className?: string;
  dense?: boolean;
}

export function DataTable<T>({
  data,
  columns,
  rowKey,
  onRowClick,
  searchable,
  searchPlaceholder = "Search…",
  initialSort,
  emptyMessage = "No matching rows",
  className,
  dense,
}: DataTableProps<T>) {
  const [sort, setSort] = useState<typeof initialSort>(initialSort);
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    if (!query) return data;
    const q = query.toLowerCase();
    return data.filter((row) =>
      columns.some((c) => {
        const v = c.accessor(row);
        return v != null && String(v).toLowerCase().includes(q);
      }),
    );
  }, [data, columns, query]);

  const sorted = useMemo(() => {
    if (!sort) return filtered;
    const col = columns.find((c) => c.id === sort.id);
    if (!col) return filtered;
    const dir = sort.dir === "asc" ? 1 : -1;
    return [...filtered].sort((a, b) => {
      const av = col.accessor(a);
      const bv = col.accessor(b);
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * dir;
      return String(av).localeCompare(String(bv)) * dir;
    });
  }, [filtered, columns, sort]);

  function toggleSort(id: string) {
    setSort((cur) => {
      if (!cur || cur.id !== id) return { id, dir: "asc" };
      if (cur.dir === "asc") return { id, dir: "desc" };
      return undefined;
    });
  }

  return (
    <div className={clsx("flex flex-col gap-3", className)}>
      {searchable && (
        <div className="relative max-w-sm">
          <Search
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-fabric-gray-130"
          />
          <Input
            placeholder={searchPlaceholder}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="pl-8"
          />
        </div>
      )}
      <div className="overflow-auto rounded-md border border-fabric-gray-30 bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-fabric-gray-10 text-fabric-gray-130">
            <tr>
              {columns.map((c) => {
                const isSorted = sort?.id === c.id;
                const Icon = !c.sortable
                  ? null
                  : isSorted
                    ? sort?.dir === "asc"
                      ? ChevronUp
                      : ChevronDown
                    : ChevronsUpDown;
                return (
                  <th
                    key={c.id}
                    style={c.width ? { width: c.width } : undefined}
                    className={clsx(
                      "text-left px-3 py-2 text-xs font-semibold uppercase tracking-wide whitespace-nowrap",
                      c.align === "right" && "text-right",
                      c.align === "center" && "text-center",
                      c.sortable && "cursor-pointer select-none hover:text-fabric-gray-190",
                    )}
                    onClick={() => c.sortable && toggleSort(c.id)}
                  >
                    <span className="inline-flex items-center gap-1">
                      {c.header}
                      {Icon && <Icon size={12} />}
                    </span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="p-0">
                  <EmptyState message={emptyMessage} />
                </td>
              </tr>
            ) : (
              sorted.map((row) => (
                <tr
                  key={rowKey(row)}
                  onClick={() => onRowClick?.(row)}
                  className={clsx(
                    "border-t border-fabric-gray-20 transition-colors",
                    onRowClick && "cursor-pointer hover:bg-fabric-blue-light/40",
                  )}
                >
                  {columns.map((c) => (
                    <td
                      key={c.id}
                      className={clsx(
                        dense ? "px-3 py-1.5" : "px-3 py-2.5",
                        "align-middle text-fabric-gray-190",
                        c.align === "right" && "text-right tabular-nums",
                        c.align === "center" && "text-center",
                        c.className,
                      )}
                    >
                      {c.cell ? c.cell(row) : (c.accessor(row) as ReactNode)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
