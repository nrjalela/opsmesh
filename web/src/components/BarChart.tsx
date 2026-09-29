import { useState } from "react";
import { money } from "../format";

export interface Bar {
  label: string;
  value: number;
  extra: number; // invoice value, shown in the tooltip
}

/** Single-series horizontal bars: one accent colour, value at the tip, tooltip on hover/focus. */
export function BarChart({ data, caption }: { data: Bar[]; caption: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const sorted = [...data].sort((a, b) => b.value - a.value || a.label.localeCompare(b.label));
  const max = Math.max(1, ...sorted.map((d) => d.value));
  const ticks = Array.from({ length: max + 1 }, (_, i) => i).filter((t) => max <= 6 || t % 2 === 0);
  const row = 44;
  const barH = 20;
  const labelW = 210;
  const plotW = 460;
  const width = labelW + plotW + 40;
  const height = sorted.length * row + 28;
  const x = (v: number) => labelW + (v / max) * plotW;

  return (
    <figure className="chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={caption} className="chart-svg">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={0} y2={height - 24} className="gridline" />
            <text x={x(t)} y={height - 6} className="tick" textAnchor="middle">
              {t}
            </text>
          </g>
        ))}
        {sorted.map((d, i) => {
          const y = i * row + (row - barH) / 2;
          const w = Math.max(2, x(d.value) - labelW);
          const r = Math.min(4, w / 2);
          // square at the baseline, 4px rounded at the data end
          const path = `M${labelW},${y} h${w - r} a${r},${r} 0 0 1 ${r},${r} v${barH - 2 * r} a${r},${r} 0 0 1 ${-r},${r} h${-(w - r)} Z`;
          return (
            <g
              key={d.label}
              className={`bar-row ${hover === i ? "is-hover" : ""}`}
              tabIndex={0}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
              onFocus={() => setHover(i)}
              onBlur={() => setHover(null)}
            >
              <rect x={0} y={i * row} width={width} height={row} className="hit" />
              <text x={labelW - 12} y={y + barH / 2} className="bar-label" textAnchor="end" dominantBaseline="central">
                {d.label}
              </text>
              <path d={path} className="bar" />
              <text x={labelW + w + 8} y={y + barH / 2} className="bar-value" dominantBaseline="central">
                {d.value}
              </text>
              <title>{`${d.label}: ${d.value} invoice${d.value === 1 ? "" : "s"}, ${money(d.extra)}`}</title>
            </g>
          );
        })}
      </svg>
      {hover !== null && (
        <div className="chart-tip" style={{ top: `${((hover * row) / height) * 100}%` }} aria-hidden="true">
          <strong>{sorted[hover].label}</strong>
          <span>
            {sorted[hover].value} invoice{sorted[hover].value === 1 ? "" : "s"} · {money(sorted[hover].extra)}
          </span>
        </div>
      )}
      <figcaption className="sr-only">{caption}</figcaption>
    </figure>
  );
}
