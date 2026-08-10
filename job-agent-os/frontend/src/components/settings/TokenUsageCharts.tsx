"use client";

import type { TokenUsageByAgent } from "@/lib/api/monitoring";

const PIE_COLORS = [
  "#3b82f6",
  "#8b5cf6",
  "#ec4899",
  "#f59e0b",
  "#10b981",
  "#06b6d4",
  "#ef4444",
];

/** Simple SVG donut chart for agent distribution. */
export function AgentDonutChart({ data }: { data: TokenUsageByAgent[] }) {
  const total = data.reduce((sum, d) => sum + d.tokens, 0);

  if (total === 0 || data.length === 0) {
    return (
      <p className="py-8 text-center text-xs text-muted-foreground">暂无 Agent 用量数据</p>
    );
  }

  const size = 160;
  const stroke = 28;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;

  let offset = 0;
  const segments = data.map((d, i) => {
    const fraction = d.tokens / total;
    const dash = fraction * circumference;
    const seg = {
      agent: d.agent,
      tokens: d.tokens,
      color: PIE_COLORS[i % PIE_COLORS.length],
      dash,
      offset,
      percent: Math.round(fraction * 100),
    };
    offset += dash;
    return seg;
  });

  return (
    <div className="flex flex-col items-center gap-4 sm:flex-row">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="shrink-0">
        <g transform={`rotate(-90 ${size / 2} ${size / 2})`}>
          {segments.map((s) => (
            <circle
              key={s.agent}
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke={s.color}
              strokeWidth={stroke}
              strokeDasharray={`${s.dash} ${circumference - s.dash}`}
              strokeDashoffset={-s.offset}
            />
          ))}
        </g>
        <text
          x="50%"
          y="47%"
          textAnchor="middle"
          className="fill-foreground text-sm font-bold"
          fontSize="16"
        >
          {total.toLocaleString()}
        </text>
        <text x="50%" y="60%" textAnchor="middle" className="fill-muted-foreground" fontSize="10">
          总 Tokens
        </text>
      </svg>

      {/* Legend */}
      <div className="flex-1 space-y-1.5">
        {segments.map((s) => (
          <div key={s.agent} className="flex items-center gap-2 text-xs">
            <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: s.color }} />
            <span className="flex-1 truncate capitalize">{s.agent}</span>
            <span className="text-muted-foreground">{s.percent}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Simple SVG line/area chart for daily usage. */
export function DailyUsageChart({ data }: { data: { date: string; tokens: number }[] }) {
  if (!data || data.length === 0) {
    return <p className="py-8 text-center text-xs text-muted-foreground">暂无每日用量数据</p>;
  }

  const width = 320;
  const height = 120;
  const padding = 8;
  const max = Math.max(...data.map((d) => d.tokens), 1);

  const points = data.map((d, i) => {
    const x = padding + (i / Math.max(data.length - 1, 1)) * (width - padding * 2);
    const y = height - padding - (d.tokens / max) * (height - padding * 2);
    return { x, y, ...d };
  });

  const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x},${p.y}`).join(" ");
  const areaPath = `${linePath} L${points[points.length - 1].x},${height - padding} L${points[0].x},${height - padding} Z`;

  return (
    <div>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full">
        <path d={areaPath} fill="hsl(var(--primary))" opacity="0.12" />
        <path d={linePath} fill="none" stroke="hsl(var(--primary))" strokeWidth="2" strokeLinejoin="round" />
        {points.map((p) => (
          <circle key={p.date} cx={p.x} cy={p.y} r="3" fill="hsl(var(--primary))" />
        ))}
      </svg>
      <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
        <span>{data[0].date}</span>
        <span>{data[data.length - 1].date}</span>
      </div>
    </div>
  );
}
