import type { ReactNode } from "react";

interface DataPoint {
  [key: string]: string | number;
}

interface SimpleBarsProps {
  data: DataPoint[];
  xKey: string;
  yKey: string;
  color?: string;
  height?: number;
}

export function SimpleBars({ data, xKey, yKey, color = "#3b82f6", height = 150 }: SimpleBarsProps) {
  if (!data.length) return <div className="text-center text-gray-400 py-8">Sin datos</div>;
  const max = Math.max(...data.map((d) => Number(d[yKey])));
  const barWidth = Math.max(8, Math.floor(600 / data.length) - 4);
  return (
    <svg width="100%" height={height} className="w-full">
      {data.map((d, i) => {
        const h = max > 0 ? (Number(d[yKey]) / max) * (height - 20) : 0;
        const x = i * (barWidth + 4) + 20;
        const y = height - h - 10;
        return (
          <rect
            key={i}
            x={x}
            y={y}
            width={barWidth}
            height={h}
            fill={color}
            rx={2}
          />
        );
      })}
    </svg>
  );
}

interface LineSparkProps {
  data: DataPoint[];
  xKey: string;
  yKey: string;
  color?: string;
  height?: number;
}

export function LineSpark({ data, xKey, yKey, color = "#ec4899", height = 150 }: LineSparkProps) {
  if (!data.length) return <div className="text-center text-gray-400 py-8">Sin datos</div>;
  const values = data.map((d) => Number(d[yKey]));
  const max = Math.max(...values);
  const min = Math.min(...values);
  const range = max - min || 1;
  const stepX = 600 / Math.max(1, data.length - 1);
  const points = data.map((d, i) => {
    const x = i * stepX + 20;
    const y = height - 10 - ((Number(d[yKey]) - min) / range) * (height - 20);
    return `${x},${y}`;
  }).join(" ");
  return (
    <svg width="100%" height={height} className="w-full">
      <polyline fill="none" stroke={color} strokeWidth={2} points={points} />
    </svg>
  );
}

interface SimplePieProps {
  data: { name: string; value: number; color: string }[];
  height?: number;
}

export function SimplePie({ data, height = 150 }: SimplePieProps) {
  if (!data.length) return <div className="text-center text-gray-400 py-8">Sin datos</div>;
  const total = data.reduce((a, d) => a + d.value, 0);
  let start = -90;
  return (
    <svg width={height} height={height} viewBox={`0 0 ${height} ${height}`} className="mx-auto">
      {data.map((d, i) => {
        const sweep = (d.value / total) * 360;
        const large = sweep > 180 ? 1 : 0;
        const rad = (start + sweep) * Math.PI / 180;
        const x1 = height / 2 + (height / 2 - 10) * Math.cos(start * Math.PI / 180);
        const y1 = height / 2 + (height / 2 - 10) * Math.sin(start * Math.PI / 180);
        const x2 = height / 2 + (height / 2 - 10) * Math.cos(rad);
        const y2 = height / 2 + (height / 2 - 10) * Math.sin(rad);
        start += sweep;
        return (
          <path
            key={i}
            d={`M ${height / 2} ${height / 2} L ${x1} ${y1} A ${height / 2 - 10} ${height / 2 - 10} 0 ${large} 1 ${x2} ${y2} Z`}
            fill={d.color}
          />
        );
      })}
    </svg>
  );
}