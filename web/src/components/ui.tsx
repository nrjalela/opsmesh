import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { useApp } from "../app-context";
import { money } from "../format";
import { RECOMMENDATION, shortStatus, statusText } from "../model";
import type { Run } from "../types";

export function StatusPill({ run, short = false }: { run: Run; short?: boolean }) {
  const tone = run.status === "posted" ? "good" : run.status === "awaiting_approval" ? "wait" : "neutral";
  const glyph = run.status === "posted" ? "✓" : run.status === "awaiting_approval" ? "◷" : "⊘";
  return (
    <span className={`pill pill-${tone}`} title={statusText(run)}>
      <span aria-hidden="true">{glyph}</span> {short ? shortStatus(run) : statusText(run)}
    </span>
  );
}

export function Confidence({ value }: { value: number }) {
  const low = value < 0.8;
  return (
    <span className={`conf ${low ? "conf-low" : ""}`} title={`${Math.round(value * 100)}% confident`}>
      <span className="conf-track" aria-hidden="true">
        <span className="conf-fill" style={{ width: `${Math.round(value * 100)}%` }} />
      </span>
      <span className="conf-num">{Math.round(value * 100)}%</span>
    </span>
  );
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    (ref.current?.querySelector<HTMLElement>("textarea, input") ?? ref.current?.querySelector<HTMLElement>("button"))?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.classList.add("no-scroll");
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.classList.remove("no-scroll");
      prev?.focus?.();
    };
  }, [onClose]);
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby={titleId} ref={ref}>
        <div className="modal-head">
          <h2 id={titleId}>{title}</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

/** Approve / reject with a note. Decisions live in this browser only. */
export function DecisionForm({ run, onDone }: { run: Run; onDone?: (msg: string) => void }) {
  const { decide } = useApp();
  const [note, setNote] = useState("");
  const pending = run.pending!;
  const noteId = useId();
  const submit = (decision: "approve" | "reject") => {
    decide(run.doc_id, decision, note, pending.approver);
    onDone?.(
      decision === "approve"
        ? `Approved ${run.doc_id} and posted ${money(run.state.invoice?.total)}.`
        : `Rejected ${run.doc_id}.`,
    );
  };
  return (
    <div className="decision">
      {pending.recommendation && (
        <p className="suggested">
          <span className="kicker">Suggested</span> {RECOMMENDATION[pending.recommendation]}
        </p>
      )}
      <label htmlFor={noteId} className="field-label">
        Note for the audit trail
      </label>
      <textarea
        id={noteId}
        rows={2}
        value={note}
        placeholder="e.g. Buyer confirmed the new price by email"
        onChange={(e) => setNote(e.target.value)}
      />
      <div className="decision-actions">
        <button className="btn btn-primary" onClick={() => submit("approve")}>
          Approve and post
        </button>
        <button className="btn" onClick={() => submit("reject")}>
          Reject
        </button>
      </div>
      <p className="hint">Your decisions are saved in this browser only. Nobody else sees them.</p>
    </div>
  );
}

export function Toast({ message, onClear }: { message: string | null; onClear: () => void }) {
  useEffect(() => {
    if (!message) return;
    const t = setTimeout(onClear, 3500);
    return () => clearTimeout(t);
  }, [message, onClear]);
  return (
    <div className="toast-region" role="status" aria-live="polite">
      {message && <div className="toast">{message}</div>}
    </div>
  );
}
