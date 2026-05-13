import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatCurrency } from "@/utils/format";

export interface TopAgentDatum {
  name: string;
  cost: number;
}

export interface TopAgentsBarChartProps {
  data: TopAgentDatum[];
  height?: number;
  max?: number;
}

const PALETTE = ["#0078d4", "#106ebe", "#2b88d8", "#71afe5", "#a9d3f2"];

export function TopAgentsBarChart({ data, height = 280, max = 5 }: TopAgentsBarChartProps) {
  const trimmed = [...data].sort((a, b) => b.cost - a.cost).slice(0, max).reverse();
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart
        layout="vertical"
        data={trimmed}
        margin={{ top: 4, right: 16, bottom: 0, left: 8 }}
      >
        <CartesianGrid stroke="#edebe9" strokeDasharray="3 3" horizontal={false} />
        <XAxis
          type="number"
          stroke="#605e5c"
          fontSize={11}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v: number) => formatCurrency(v, { compact: true })}
        />
        <YAxis
          dataKey="name"
          type="category"
          stroke="#323130"
          fontSize={12}
          tickLine={false}
          axisLine={false}
          width={140}
        />
        <Tooltip formatter={(v: number) => formatCurrency(v)} />
        <Bar dataKey="cost" radius={[0, 4, 4, 0]}>
          {trimmed.map((_, i) => (
            <Cell key={i} fill={PALETTE[(trimmed.length - 1 - i) % PALETTE.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
