import { useState } from "react";
import { useApp } from "../app-context";
import { StatusPill } from "../components/ui";
import { day, money } from "../format";
import { issueText, totalOf, vendorOf } from "../model";
import { go, href } from "../router";
import type { RunStatus } from "../types";

const FILTERS: { label: string; status: RunStatus | null }[] = [
  { label: "All", status: null },
  { label: "Waiting for approval", status: "awaiting_approval" },
  { label: "Posted", status: "posted" },
  { label: "Rejected", status: "rejected" },
];

export function QueuePage() {
  const { batch, runs } = useApp();
  const [filter, setFilter] = useState<RunStatus | null>(null);
  const count = (s: RunStatus) => runs.filter((r) => r.status === s).length;
  const shown = filter ? runs.filter((r) => r.status === filter) : runs;
  const s = batch.summary;

  return (
    <>
      <section className="intro">
        <p className="kicker">Procure-to-pay automation · recorded run</p>
        <h1>Invoice queue</h1>
        <p className="lede">
          {s.invoices} supplier invoices received by Corio Packaging's accounts payable team in September 2026. For
          each one, a Claude agent read the PDF, plain code ran the three-way match against the purchase order and
          goods receipt, and a rules-based router decided whether a person needed to look. Open any invoice to see
          every step, or try the approval inbox.
        </p>
      </section>

      <div className="toolbar">
        <p className="counts">
          <strong>{runs.length}</strong> invoices · <strong>{count("posted")}</strong> posted ·{" "}
          <strong>{count("awaiting_approval")}</strong> waiting for approval · <strong>{count("rejected")}</strong>{" "}
          rejected
        </p>
        <div className="segmented" role="group" aria-label="Filter by status">
          {FILTERS.map((f) => (
            <button key={f.label} aria-pressed={filter === f.status} onClick={() => setFilter(f.status)}>
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <div className="table-wrap">
        <table className="table queue">
          <thead>
            <tr>
              <th className="hide-sm">Doc</th>
              <th className="hide-sm">Received</th>
              <th>Vendor</th>
              <th className="hide-lg">Invoice no.</th>
              <th className="num">Total</th>
              <th className="hide-sm">Status</th>
              <th className="hide-md">What stopped it</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr
                key={r.doc_id}
                className="clickable"
                onClick={() => go({ page: "invoice", id: r.doc_id })}
              >
                <td className="nowrap hide-sm">
                  <a href={href({ page: "invoice", id: r.doc_id })} onClick={(e) => e.stopPropagation()}>
                    {r.doc_id}
                  </a>
                </td>
                <td className="nowrap hide-sm">{day(r.received_date, false)}</td>
                <td className="vendor" title={vendorOf(r)}>
                  {vendorOf(r).replace(/ Pty\.? Ltd\.?$/i, "")}
                  <span className="show-sm muted small block">{r.doc_id}</span>
                  <span className="show-sm stack-pill">
                    <StatusPill run={r} short />
                  </span>
                </td>
                <td className="hide-lg mono nowrap">{r.state.invoice?.invoice_number ?? "–"}</td>
                <td className="num">{money(totalOf(r))}</td>
                <td className="hide-sm">
                  <StatusPill run={r} short />
                </td>
                <td className="hide-md muted">{issueText(batch, r)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {shown.length === 0 && <p className="empty">Nothing here.</p>}
      </div>
    </>
  );
}
