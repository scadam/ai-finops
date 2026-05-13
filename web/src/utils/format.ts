export function toNum(v: string | number | null | undefined): number {
  if (v === null || v === undefined || v === "") return 0;
  if (typeof v === "number") return Number.isFinite(v) ? v : 0;
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

export function formatCurrency(
  v: string | number | null | undefined,
  opts: { decimals?: number; compact?: boolean } = {},
): string {
  const n = toNum(v);
  const { decimals, compact } = opts;
  if (compact) {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      notation: "compact",
      maximumFractionDigits: 1,
    }).format(n);
  }
  const abs = Math.abs(n);
  const d = decimals ?? (abs < 10 ? 2 : abs < 1000 ? 2 : 0);
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  }).format(n);
}

export function formatNumber(
  n: number | string | null | undefined,
  opts: { compact?: boolean; decimals?: number } = {},
): string {
  const v = toNum(n);
  if (opts.compact) {
    return new Intl.NumberFormat("en-US", {
      notation: "compact",
      maximumFractionDigits: opts.decimals ?? 1,
    }).format(v);
  }
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: opts.decimals ?? 0,
  }).format(v);
}

export function formatPct(n: number | string | null | undefined, decimals = 1): string {
  const v = toNum(n);
  return `${v.toFixed(decimals)}%`;
}

export function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const ts = new Date(iso).getTime();
  if (Number.isNaN(ts)) return "—";
  const diff = Date.now() - ts;
  const future = diff < 0;
  const s = Math.abs(Math.floor(diff / 1000));
  const fmt = (val: number, unit: string) =>
    `${val}${unit}${future ? " from now" : " ago"}`;
  if (s < 60) return fmt(s, "s");
  const m = Math.floor(s / 60);
  if (m < 60) return fmt(m, "m");
  const h = Math.floor(m / 60);
  if (h < 24) return fmt(h, "h");
  const d = Math.floor(h / 24);
  if (d < 30) return fmt(d, "d");
  const mo = Math.floor(d / 30);
  if (mo < 12) return fmt(mo, "mo");
  const y = Math.floor(d / 365);
  return fmt(y, "y");
}

export function titleCase(s: string | null | undefined): string {
  if (!s) return "";
  return s
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
