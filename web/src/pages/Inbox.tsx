import { useState } from "react";
import { useApp } from "../app-context";
import { DecisionForm, Modal } from "../components/ui";
import { money } from "../format";
import { issueText, totalOf, vendorOf } from "../model";
import { href } from "../router";

export function InboxPage({ onToast }: { onToast: (m: string) => void }) {
  const { batch, runs, byId, decisions, undo, resetAll } = useApp();
  const [reviewing, setReviewing] = useState<string | null>(null);
  const waiting = runs.filter((r) => r.status === "awaiting_approval");
  const decided = Object.keys(decisions).filter((id) => byId[id]);
  const current = reviewing ? byId[reviewing] : null;

  return (
    <>
      <section className="intro">
        <p className="kicker">Human in the loop</p>
        <h1>Approval inbox</h1>
        <p className="lede">
          Invoices the approval router paused for a person: anything with an exception, anything the intake agent
          wasn't sure about, and clean invoices over the auto-post limit. Approve or reject with a note. Your
          decisions stay in this browser.
        </p>
      </section>

      {waiting.length === 0 && <p className="panel">Inbox zero. Every invoice has been decided.</p>}

      {batch.roles.map((role) => {
        const mine = waiting.filter((r) => r.pending?.approver === role);
        if (!mine.length) return null;
        return (
          <section key={role} className="section">
            <h2>
              {role} <span className="muted count-label">{mine.length} waiting</span>
            </h2>
            <ul className="cards">
              {mine.map((r) => (
                <li key={r.doc_id} className="card">
                  <div className="card-main">
                    <p className="card-title">
                      <strong>{vendorOf(r)}</strong> <span className="amount">{money(totalOf(r))}</span>
                    </p>
                    <p className="muted small">
                      {r.doc_id} · invoice {r.state.invoice?.invoice_number ?? "?"} · {issueText(batch, r)}
                    </p>
                    <p>{r.state.analysis?.headline ?? r.pending?.reasons.join(" ")}</p>
                  </div>
                  <div className="card-actions">
                    <button className="btn" onClick={() => setReviewing(r.doc_id)}>
                      Review
                    </button>
                    <a className="btn btn-quiet" href={href({ page: "invoice", id: r.doc_id })}>
                      Open invoice
                    </a>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        );
      })}

      {decided.length > 0 && (
        <section className="section">
          <div className="section-head">
            <h2>Decided in this browser</h2>
            <button className="btn btn-quiet" onClick={resetAll}>
              Reset all
            </button>
          </div>
          <ul className="decided">
            {decided.map((id) => {
              const r = byId[id];
              const d = decisions[id];
              return (
                <li key={id}>
                  <span>
                    {d.decision === "approve" ? "Posted" : "Rejected"} <strong>{vendorOf(r)}</strong>{" "}
                    {money(totalOf(r))} <span className="muted">{id}</span>
                    {d.note && <span className="muted"> · “{d.note}”</span>}
                  </span>
                  <button className="btn btn-quiet" onClick={() => undo(id)}>
                    Undo
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {current?.pending && (
        <Modal title="Review invoice" onClose={() => setReviewing(null)}>
          <p className="card-title">
            <strong>{vendorOf(current)}</strong> <span className="amount">{money(totalOf(current))}</span>
          </p>
          <p className="muted small">
            {current.doc_id} · invoice {current.state.invoice?.invoice_number}
          </p>
          <ul className="reasons">
            {current.pending.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
          {current.state.analysis && <p>{current.state.analysis.explanation}</p>}
          <DecisionForm
            run={current}
            onDone={(m) => {
              setReviewing(null);
              onToast(m);
            }}
          />
        </Modal>
      )}
    </>
  );
}
