import { Cell, Pie, PieChart, ResponsiveContainer } from "recharts";

export interface LicenseUtilGaugeProps {
  pct: number; // 0-100
  height?: number;
  label?: string;
}

function colorFor(p: number): string {
  if (p >= 85) return "#107c10";
  if (p >= 60) return "#ffaa44";
  return "#d13438";
}

export function LicenseUtilGauge({ pct, height = 200, label }: LicenseUtilGaugeProps) {
  const v = Math.max(0, Math.min(100, Number.isFinite(pct) ? pct : 0));
  const data = [
    { name: "u", value: v },
    { name: "r", value: 100 - v },
  ];
  const fill = colorFor(v);
  return (
    <div className="relative w-full" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="80%"
            innerRadius="80%"
            outerRadius="120%"
            startAngle={180}
            endAngle={0}
            dataKey="value"
            stroke="none"
            isAnimationActive={false}
          >
            <Cell fill={fill} />
            <Cell fill="#edebe9" />
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      <div className="absolute inset-0 flex flex-col items-center justify-end pb-3 pointer-events-none">
        <span
          className="text-3xl font-semibold tabular-nums"
          style={{ color: fill }}
        >
          {v.toFixed(0)}%
        </span>
        <span className="text-[11px] text-fabric-gray-130 mt-0.5">
          {label ?? "License utilisation"}
        </span>
      </div>
    </div>
  );
}
