import type { Batch, Decision, Run, Step } from "./types";

// --- decisions: kept in this browser only --------------------------------------------------

const STORAGE_KEY = "opsmesh.decisions.v1";

export function loadDecisions(): Record<string, Decision> {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Record<string, Decision>) : {};
  } catch {
    return {}; // private mode, blocked storage, or corrupt value: start fresh
  }
}

export function saveDecisions(decisions: Record<string, Decision>): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(decisions));
  } catch {
    // Decisions still work for this page view; they just won't survive a reload.
  }
}

/** Replay a visitor's decision onto a paused run, using the outcome Python precomputed. */
export function applyDecision(batch: Batch, run: Run, d: Decision): Run {
  const preview = batch.decision_previews[run.doc_id]?.[d.decision];
  if (!run.pending || !preview) return run;
  const note = d.note.trim() || null;
  const human: Step = {
    node: "human_review",
    title: "Human approval",
    kind: "human",
    started_at: d.decidedAt,
    duration_ms: 0,
    summary: `${d.decision === "approve" ? "Approved" : "Rejected"} by ${d.reviewer}.${note ? ` "${note}"` : ""}`,
    reasoning: note ?? "",
    trace: [],
    model: null,
    input_tokens: 0,
    output_tokens: 0,
    cost_usd: 0,
    error: null,
  };
  const outcome =
    preview.outcome.status === "posted"
      ? { ...preview.outcome, approved_by: d.reviewer, note }
      : { ...preview.outcome, rejected_by: d.reviewer, note };
  return {
    ...run,
    status: outcome.status,
    pending: null,
    state: { ...run.state, decision: { decision: d.decision, note, reviewer: d.reviewer }, outcome },
    steps: [...run.steps, human, { ...preview.step, started_at: d.decidedAt }],
  };
}

export function withDecisions(batch: Batch, decisions: Record<string, Decision>): Run[] {
  return batch.runs.map((r) => (decisions[r.doc_id] ? applyDecision(batch, r, decisions[r.doc_id]) : r));
}

// --- describing a run ---------------------------------------------------------------------

export function vendorOf(run: Run): string {
  return (
    run.state.match?.vendor_name ??
    run.state.invoice?.vendor_name ??
    run.state.extraction?.vendor_name.value ??
    "Unreadable document"
  );
}

export function totalOf(run: Run): number | null {
  const t = run.state.invoice?.total;
  return t === undefined || t === null ? null : Number(t);
}

export function exceptionTypes(run: Run): string[] {
  const seen: string[] = [];
  for (const e of run.state.match?.exceptions ?? []) if (!seen.includes(e.type)) seen.push(e.type);
  return seen;
}

export function isTouchless(run: Run): boolean {
  return run.state.route?.action === "auto_post";
}

export function statusText(run: Run): string {
  switch (run.status) {
    case "posted":
      return isTouchless(run) ? "Posted, no human touch" : "Posted after approval";
    case "awaiting_approval":
      return `Waiting on ${run.pending?.approver ?? "a person"}`;
    case "rejected":
      return "Rejected";
    default:
      return "Needs attention";
  }
}

export function shortStatus(run: Run): string {
  switch (run.status) {
    case "posted":
      return isTouchless(run) ? "Auto-posted" : "Approved";
    case "awaiting_approval":
      return `Waiting: ${run.pending?.approver ?? "person"}`;
    case "rejected":
      return "Rejected";
    default:
      return "Needs attention";
  }
}

export function issueText(batch: Batch, run: Run): string {
  const types = exceptionTypes(run);
  if (types.length) return types.map((t) => batch.exception_labels[t]?.label ?? t).join(", ");
  const route = run.state.route;
  if (route?.action === "needs_approval") {
    const reasons = route.reasons.join(" ");
    if (reasons.includes("Low-confidence")) return "Agent unsure of a field";
    if (reasons.includes("auto-post limit")) return "High value";
    return "Needs a person";
  }
  return "";
}

export const RECOMMENDATION: Record<string, string> = {
  approve: "Approve: clean three-way match, held only because of the amount",
  reject: "Reject: this invoice was already posted",
  resolve_first: "Hold until the issue is sorted",
};

export const KIND_LABEL: Record<string, string> = { llm: "AI agent", code: "Rules", human: "Person" };
