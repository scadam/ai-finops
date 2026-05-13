import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { CostTrendPoint } from "@/types/api";
import { formatCurrency, toNum } from "@/utils/format";

export interface SpendAreaChartProps {
  data: CostTrendPoint[];
  height?: number;
}

const fmtPeriod = (s: string) => {
  if (!s) return "";
  const [y, m] = s.split("-");
  const d = new Date(Number(y), Number(m) - 1, 1);
  return d.toLocaleString("en-US", { month: "short", year: "2-digit" });
};

export function SpendAreaChart({ data, height = 280 }: SpendAreaChartProps) {
  const chartData = data.map((d) => ({
    period: fmtPeriod(d.period),
    License: toNum(d.license_cost_usd),
    Credits: toNum(d.credits_cost_usd),
    Azure: toNum(d.azure_cost_usd),
  }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={chartData} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="g-license" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#0078d4" stopOpacity={0.45} />
            <stop offset="100%" stopColor="#0078d4" stopOpacity={0.05} />
          </linearGradient>
          <linearGradient id="g-credits" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#8a64d6" stopOpacity={0.45} />
            <stop offset="100%" stopColor="#8a64d6" stopOpacity={0.05} />
          </linearGradient>
          <linearGradient id="g-azure" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#107c10" stopOpacity={0.45} />
            <stop offset="100%" stopColor="#107c10" stopOpacity={0.05} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="#edebe9" strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="period" stroke="#605e5c" fontSize={11} tickLine={false} axisLine={false} />
        <YAxis
          stroke="#605e5c"
          fontSize={11}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v: number) => formatCurrency(v, { compact: true })}
        />
        <Tooltip
          formatter={(v: number) => formatCurrency(v)}
          labelStyle={{ color: "#323130", fontWeight: 600 }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} iconType="circle" />
        <Area
          type="monotone"
          dataKey="License"
          stroke="#0078d4"
          strokeWidth={2}
          fill="url(#g-license)"
          stackId="1"
        />
        <Area
          type="monotone"
          dataKey="Credits"
          stroke="#8a64d6"
          strokeWidth={2}
          fill="url(#g-credits)"
          stackId="1"
        />
        <Area
          type="monotone"
          dataKey="Azure"
          stroke="#107c10"
          strokeWidth={2}
          fill="url(#g-azure)"
          stackId="1"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
