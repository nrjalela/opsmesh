import { useState } from "react";
import { useApp } from "../app-context";
import { BarChart, type Bar } from "../components/BarChart";
import { duration, money, pct } from "../format";
import { exceptionTypes, isTouchless, totalOf } from "../model";

export function DashboardPage() {
  const { batch, runs } = useApp();
  const [asTable, setAsTable] = useState(false);
  const s = batch.summary;
  const ex = s.extraction;

  const touchless = runs.filter(isTouchless);
  const held = runs.filter((r) => r.status === "awaiting_approval" && exceptionTypes(r).length > 0);
  const signoff = runs.filter((r) => r.status === "awaiting_approval" && exceptionTypes(r).length === 0);
  const sum = (rs: typeof runs) => rs.reduce((acc, r) => acc + (totalOf(r) ?? 0), 0);
  const avgMs = (rs: typeof runs) => (rs.length ? rs.reduce((a, r) => a + r.metrics.automated_ms, 0) / rs.length : 0);

  const byType = new Map<string, Bar>();
  for (const r of runs) {
    for (const t of exceptionTypes(r)) {
      const label = batch.exception_labels[t]?.label ?? t;
      const bar = byType.get(label) ?? { label, value: 0, extra: 0 };
      bar.value += 1;
      bar.extra += totalOf(r) ?? 0;
      byType.set(label, bar);
    }
  }
  const bars = [...byType.values()].sort((a, b) => b.value - a.value);
  const nonTouchless = runs.filter((r) => !isTouchless(r));

  return (
    <>
      <section className="intro">
        <p className="kicker">September batch</p>
        <h1>AP dashboard</h1>
        <p className="lede">The batch at a glance. These figures update as you approve or reject in the inbox.</p>
      </section>

      <section className="kpis" aria-label="Key figures">
        <div className="kpi">
          <span className="kpi-label">Touchless rate</span>
          <span className="kpi-value">{pct(touchless.length / runs.length)}</span>
          <span className="kpi-note">
            {touchless.length} of {runs.length} invoices posted with no human touch
          </span>
        </div>
        <div className="kpi">
          <span className="kpi-label">Avg cycle time, touchless</span>
          <span className="kpi-value">{duration(Math.round(avgMs(touchless)))}</span>
          <span className="kpi-note">PDF received to posted, measured on the recorded runs</span>
        </div>
        <div className="kpi">
          <span className="kpi-label">Value on hold</span>
          <span className="kpi-value">{money(sum(held))}</span>
          <span className="kpi-note">
            {held.length} invoices blocked by exceptions · {money(sum(signoff))} more awaiting sign-off
          </span>
        </div>
        <div className="kpi">
          <span className="kpi-label">Extraction accuracy</span>
          <span className="kpi-value">{pct(ex.field_accuracy, ex.field_accuracy < 1 ? 1 : 0)}</span>
          <span className="kpi-note">
            {ex.fields_correct} of {ex.fields_total} fields read from the PDFs match the answer key
          </span>
        </div>
      </section>

      <div className="dash-grid">
        <section className="panel">
          <div className="section-head">
            <div>
              <h2>Exceptions caught, by type</h2>
              <p className="muted small">Invoices stopped by the three-way match. One invoice can have more than one.</p>
            </div>
            <button className="btn btn-quiet" onClick={() => setAsTable((v) => !v)} aria-pressed={asTable}>
              {asTable ? "Show chart" : "Show table"}
            </button>
          </div>
          {asTable ? (
            <table className="table compact">
              <thead>
                <tr>
                  <th>Exception</th>
                  <th className="num">Invoices</th>
                  <th className="num">Invoice value</th>
                </tr>
              </thead>
              <tbody>
                {bars.map((b) => (
                  <tr key={b.label}>
                    <td>{b.label}</td>
                    <td className="num">{b.value}</td>
                    <td className="num">{money(b.extra)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <BarChart data={bars} caption="Number of invoices stopped, by exception type" />
          )}
        </section>

        <section className="panel stats">
          <h2>The recorded run</h2>
          <dl>
            <dt>Model</dt>
            <dd>{s.model}</dd>
            <dt>API cost, whole batch</dt>
            <dd>
              ${s.cost_usd.toFixed(2)} (${(s.cost_usd / s.invoices).toFixed(3)} per invoice)
            </dd>
            <dt>Exceptions matching the answer key</dt>
            <dd>
              {s.exceptions_match_answer_key} of {s.invoices}
            </dd>
            <dt>Invoices read perfectly</dt>
            <dd>
              {ex.invoices_all_correct} of {ex.invoices_total}
            </dd>
            <dt>Avg automated time, invoices a person saw</dt>
            <dd>{duration(Math.round(avgMs(nonTouchless)))}</dd>
          </dl>
        </section>
      </div>
    </>
  );
}
