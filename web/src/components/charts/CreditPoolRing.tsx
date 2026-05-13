import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { formatNumber } from "@/utils/format";

export interface CreditPoolRingProps {
  used: number;
  remaining: number;
  height?: number;
  centerLabel?: string;
}

export function CreditPoolRing({
  used,
  remaining,
  height = 200,
  centerLabel,
}: CreditPoolRingProps) {
  const total = used + remaining;
  const data = [
    { name: "Used", value: used },
    { name: "Remaining", value: remaining },
  ];
  const pct = total > 0 ? (used / total) * 100 : 0;
  return (
    <div className="relative w-full" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Tooltip formatter={(v: number) => formatNumber(v)} />
          <Pie
            data={data}
            innerRadius="65%"
            outerRadius="92%"
            dataKey="value"
            startAngle={90}
            endAngle={-270}
            paddingAngle={2}
            stroke="none"
            isAnimationActive={false}
          >
            <Cell fill="#0078d4" />
            <Cell fill="#deecf9" />
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
        <span className="text-2xl font-semibold text-fabric-gray-190 tabular-nums">
          {pct.toFixed(0)}%
        </span>
        <span className="text-[11px] text-fabric-gray-130 mt-1">
          {centerLabel ?? `${formatNumber(used)} / ${formatNumber(total)} credits`}
        </span>
      </div>
    </div>
  );
}
