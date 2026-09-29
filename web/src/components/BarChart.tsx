import { useEffect, useState } from "react";
import { money } from "../format";

const NARROW = "(max-width: 599px)";

function useNarrow(): boolean {
  const supported = typeof window !== "undefined" && typeof window.matchMedia === "function";
  const [narrow, setNarrow] = useState(() => supported && window.matchMedia(NARROW).matches);
  useEffect(() => {
    if (!supported) return;
    const mq = window.matchMedia(NARROW);
    const onChange = () => setNarrow(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [supported]);
  return narrow;
}

export interface Bar {
  label: string;
  value: number;
  extra: number; // invoice value, shown in the tooltip
}

/** Single-series horizontal bars: one accent colour, value at the tip, tooltip on hover/focus. */
export function BarChart({ data, caption }: { data: Bar[]; caption: string }) {
  const [hover, setHover] = useState<number | null>(null);
  // Phones: labels sit above full-width bars, and the viewBox is close to the real width,
  // so text renders near its true size instead of shrinking with the whole chart.
  const compact = useNarrow();
  const sorted = [...data].sort((a, b) => b.value - a.value || a.label.localeCompare(b.label));
  const max = Math.max(1, ...sorted.map((d) => d.value));
  const ticks = Array.from({ length: max + 1 }, (_, i) => i).filter((t) => max <= 6 || t % 2 === 0);
  const row = compact ? 52 : 44;
  const barH = compact ? 16 : 20;
  const labelW = compact ? 0 : 210;
  const plotW = compact ? 280 : 460;
  const width = labelW + plotW + (compact ? 30 : 40);
  const height = sorted.length * row + 28;
  const x = (v: number) => labelW + (v / max) * plotW;
  const barTop = (i: number) => (compact ? i * row + 26 : i * row + (row - barH) / 2);

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
          const y = barTop(i);
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
              <text
                x={compact ? 0 : labelW - 12}
                y={compact ? i * row + 14 : y + barH / 2}
                className="bar-label"
                textAnchor={compact ? "start" : "end"}
                dominantBaseline="central"
              >
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
