const aud = new Intl.NumberFormat("en-AU", { style: "currency", currency: "AUD", currencyDisplay: "narrowSymbol" });

export function money(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === "") return "–";
  return aud.format(Number(v));
}

export function moneyCompact(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (Math.abs(v) >= 10_000) return `$${(v / 1000).toFixed(1)}K`;
  return money(v);
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-09-12" -> "12 Sep 2026" without timezone surprises. */
export function day(iso: string | null | undefined, withYear = true): string {
  if (!iso) return "–";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return iso;
  return withYear ? `${d} ${MONTHS[m - 1]} ${y}` : `${d} ${MONTHS[m - 1]}`;
}

export function duration(ms: number): string {
  if (ms < 1) return "<1 ms";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

export function pct(v: number, digits = 0): string {
  return `${(v * 100).toFixed(digits)}%`;
}
