import { useState } from "react";
import { useApp } from "../app-context";
import { Confidence, DecisionForm, StatusPill } from "../components/ui";
import { day, duration, money } from "../format";
import { KIND_LABEL, totalOf, vendorOf } from "../model";
import { href } from "../router";
import type { Draft, Extraction, Run } from "../types";

const HEADER_FIELDS: [keyof Extraction, string][] = [
  ["vendor_name", "Vendor"],
  ["vendor_abn", "ABN"],
  ["invoice_number", "Invoice number"],
  ["invoice_date", "Invoice date"],
  ["po_number", "PO number"],
  ["subtotal_ex_gst", "Subtotal (ex GST)"],
  ["gst_amount", "GST"],
  ["total_inc_gst", "Total (inc GST)"],
];
const TRACE_GLYPH = { pass: "✓", fail: "✕", info: "•" } as const;
// Same line fields the router's confidence check uses (opsmesh/agents/schema.py), so the UI and routing agree.
const LINE_CHECKED = ["description", "item_code", "po_line", "quantity", "unit_price", "amount"] as const;

export function InvoicePage({ id, onToast }: { id: string; onToast: (m: string) => void }) {
  const { runs, byId } = useApp();
  const run = byId[id];
  if (!run) {
    return (
      <section className="intro">
        <h1>Invoice not found</h1>
        <p>
          There's no invoice {id} in this batch. <a href="#/">Back to the queue</a>
        </p>
      </section>
    );
  }
  const idx = runs.findIndex((r) => r.doc_id === id);
  const prev = runs[idx - 1];
  const next = runs[idx + 1];
  const inv = run.state.invoice;
  const outcome = run.state.outcome;

  return (
    <>
      <div className="crumbs">
        <a href="#/">← Invoice queue</a>
        <span className="crumbs-nav">
          {prev && <a href={href({ page: "invoice", id: prev.doc_id })}>‹ {prev.doc_id}</a>}
          {next && <a href={href({ page: "invoice", id: next.doc_id })}>{next.doc_id} ›</a>}
        </span>
      </div>

      <section className="invoice-head">
        <div>
          <p className="kicker">{run.doc_id}</p>
          <h1>{vendorOf(run)}</h1>
          <p className="muted">
            {[
              inv?.invoice_number && `Invoice ${inv.invoice_number}`,
              inv?.po_number ? `PO ${inv.po_number}` : "No PO",
              `received ${day(run.received_date)}`,
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
          <StatusPill run={run} />
        </div>
        <div className="head-total">
          <span className="kicker">Total inc GST</span>
          <span className="big-number">{money(totalOf(run))}</span>
        </div>
      </section>

      {run.pending && (
        <section className="panel panel-accent">
          <h2 className="panel-title">Waiting on the {run.pending.approver}</h2>
          <ul className="reasons">
            {run.pending.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
          <DecisionForm run={run} onDone={onToast} />
        </section>
      )}

      {outcome && (
        <section className={`banner ${outcome.status === "posted" ? "banner-good" : "banner-neutral"}`}>
          {outcome.status === "posted" ? (
            <>
              Posted as document <strong>{outcome.document_number}</strong>. {money(outcome.amount)} due for payment{" "}
              {day(outcome.due_date)}. Approved by: {outcome.approved_by}.
            </>
          ) : (
            <>Rejected by {outcome.rejected_by}. Not posted.</>
          )}
          {outcome.note && <> Note: “{outcome.note}”</>}
        </section>
      )}

      {run.state.analysis && <WhatWentWrong run={run} />}

      <section className="section">
        <h2>The invoice and what the intake agent read</h2>
        <div className="split">
          <figure className="pdf">
            <img
              src={`${import.meta.env.BASE_URL}invoices/${run.doc_id}.webp`}
              alt={`Invoice ${inv?.invoice_number ?? run.doc_id} from ${vendorOf(run)} (synthetic)`}
              loading="lazy"
            />
            <figcaption>
              <a href={`${import.meta.env.BASE_URL}invoices/${run.doc_id}.pdf`} target="_blank" rel="noreferrer">
                Open the PDF
              </a>
            </figcaption>
          </figure>
          <Extracted run={run} />
        </div>
      </section>

      <Timeline run={run} />
    </>
  );
}

function WhatWentWrong({ run }: { run: Run }) {
  const a = run.state.analysis!;
  const [tab, setTab] = useState(0);
  return (
    <section className="section">
      <h2>What went wrong</h2>
      <div className="panel">
        <p className="headline">{a.headline}</p>
        <p>{a.explanation}</p>
        <p>
          <span className="kicker">Recommended</span> {a.recommended_action}
        </p>
      </div>
      {a.drafts.length > 0 && (
        <div className="drafts">
          <div className="tabs" role="tablist">
            {a.drafts.map((d, i) => (
              <button key={i} role="tab" aria-selected={tab === i} onClick={() => setTab(i)}>
                {draftName(d)}
              </button>
            ))}
          </div>
          <DraftView draft={a.drafts[Math.min(tab, a.drafts.length - 1)]} />
        </div>
      )}
    </section>
  );
}

function draftName(d: Draft): string {
  const who = d.to.split(" <")[0].split(" (")[0];
  return `${d.kind === "vendor_email" ? "Email to" : "Note to"} ${who}`;
}

function DraftView({ draft }: { draft: Draft }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(`Subject: ${draft.subject}\n\n${draft.body}`);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };
  return (
    <div className="draft" role="tabpanel">
      <div className="draft-head">
        <div>
          <p className="muted small">To: {draft.to}</p>
          <p>
            <strong>{draft.subject}</strong>
          </p>
        </div>
        <button className="btn btn-quiet" onClick={copy}>
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="draft-body">{draft.body}</pre>
      <p className="hint">Drafted by the exception agent for a person to review. Nothing is sent automatically.</p>
    </div>
  );
}

function Extracted({ run }: { run: Run }) {
  const x = run.state.extraction;
  if (!x) return <p className="panel">The intake agent couldn't read this document.</p>;
  return (
    <div className="extracted">
      <div className="table-scroll">
      <table className="table compact">
        <thead>
          <tr>
            <th>Field</th>
            <th>Value</th>
            <th>Confidence</th>
          </tr>
        </thead>
        <tbody>
          {HEADER_FIELDS.map(([key, label]) => {
            const f = x[key] as { value: string | number | null; confidence: number };
            return (
              <tr key={key}>
                <td className="muted">{label}</td>
                <td className={key === "vendor_name" ? undefined : "mono"}>{f.value === null ? "–" : String(f.value)}</td>
                <td>
                  <Confidence value={f.confidence} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      </div>
      <div className="table-scroll">
      <table className="table compact">
        <thead>
          <tr>
            <th>Line</th>
            <th className="num">Qty</th>
            <th className="num">Price</th>
            <th className="num">Amount</th>
            <th title="Lowest confidence among the fields the router checks">Lowest confidence</th>
          </tr>
        </thead>
        <tbody>
          {x.lines.map((ln, i) => (
            <tr key={i}>
              <td>
                {ln.description.value}
                {ln.item_code.value && <span className="muted small block mono">{ln.item_code.value}</span>}
              </td>
              <td className="num">
                {ln.quantity.value} <span className="muted small">{ln.uom.value}</span>
              </td>
              <td className="num">{money(ln.unit_price.value)}</td>
              <td className="num">{money(ln.amount.value)}</td>
              <td>
                <Confidence value={Math.min(...LINE_CHECKED.map((f) => ln[f].confidence))} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      {x.remarks.value && (
        // Amber only when the match engine flagged the remark (e.g. a bank-details change); otherwise neutral.
        <p className={`callout ${remarkFlagged(run) ? "callout-warn" : ""}`}>
          {remarkFlagged(run) ? "Flagged note printed on the invoice" : "Note printed on the invoice"}: “
          {x.remarks.value}”
        </p>
      )}
      {x.notes_for_ap && <p className="muted small">Agent's note: {x.notes_for_ap}</p>}
    </div>
  );
}

function Timeline({ run }: { run: Run }) {
  const m = run.metrics;
  return (
    <section className="section">
      <h2>How it was processed</h2>
      <p className="muted">
        {run.steps.length} steps · {duration(m.automated_ms)} of automated work · API cost ${m.cost_usd.toFixed(3)}
      </p>
      <ol className="timeline">
        {run.steps.map((s, i) => (
          <li key={i} className={`step step-${s.kind}`}>
            <div className="step-marker" aria-hidden="true" />
            <div className="step-body">
              <div className="step-head">
                <span className="step-title">{s.title}</span>
                <span className={`tag tag-${s.kind}`}>{KIND_LABEL[s.kind]}</span>
                {!(s.kind === "human") && <span className="step-time">{duration(s.duration_ms)}</span>}
              </div>
              <p>{s.summary}</p>
              {s.error && <p className="error">{s.error}</p>}
              {(s.reasoning || s.trace.length > 0) && (
                <details>
                  <summary>Why</summary>
                  {s.reasoning && <p className="reasoning">{s.reasoning}</p>}
                  {s.trace.length > 0 && (
                    <ul className="trace">
                      {s.trace.map((t, j) => (
                        <li key={j} className={`trace-${t.outcome}`}>
                          <span className="trace-glyph" aria-label={t.outcome}>
                            {TRACE_GLYPH[t.outcome]}
                          </span>
                          <span>
                            <strong>{t.check}:</strong> {t.detail}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                  {s.kind === "llm" && (
                    <p className="muted small">
                      {s.model} · {s.input_tokens.toLocaleString()} tokens in, {s.output_tokens.toLocaleString()} out ·
                      ${s.cost_usd.toFixed(4)}
                    </p>
                  )}
                </details>
              )}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function remarkFlagged(run: Run): boolean {
  return (run.state.match?.exceptions ?? []).some((e) => e.details?.bank_details_change);
}
