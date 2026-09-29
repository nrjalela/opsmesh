// Shapes of web/public/data/batch.json, written by `python -m opsmesh.replay.export_web`.

export type Outcome = "pass" | "fail" | "info";
export type StepKind = "llm" | "code" | "human";
export type RunStatus = "posted" | "awaiting_approval" | "rejected" | "error";

export interface TraceStep {
  check: string;
  outcome: Outcome;
  detail: string;
}

export interface Step {
  node: string;
  title: string;
  kind: StepKind;
  started_at: string;
  duration_ms: number;
  summary: string;
  reasoning: string;
  trace: TraceStep[];
  model: string | null;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  error: string | null;
}

export interface Field<T> {
  value: T | null;
  confidence: number;
}

export interface ExtractedLine {
  description: Field<string>;
  item_code: Field<string>;
  po_line: Field<number>;
  quantity: Field<number>;
  uom: Field<string>;
  unit_price: Field<number>;
  amount: Field<number>;
  gst_applicable: Field<boolean>;
}

export interface Extraction {
  is_tax_invoice: boolean;
  vendor_name: Field<string>;
  vendor_abn: Field<string>;
  invoice_number: Field<string>;
  invoice_date: Field<string>;
  due_date: Field<string>;
  po_number: Field<string>;
  currency: Field<string>;
  lines: ExtractedLine[];
  subtotal_ex_gst: Field<number>;
  gst_amount: Field<number>;
  total_inc_gst: Field<number>;
  remarks: Field<string>;
  notes_for_ap: string;
}

export interface Invoice {
  vendor_name: string;
  vendor_abn: string;
  invoice_number: string;
  invoice_date: string;
  po_number: string | null;
  total: string;
  subtotal: string;
  gst_amount: string;
}

export interface MatchException {
  type: string;
  message: string;
  line: number | null;
  details: Record<string, string>;
}

export interface Match {
  vendor_id: string | null;
  vendor_name: string | null;
  po_number: string | null;
  exceptions: MatchException[];
}

export interface Draft {
  kind: "vendor_email" | "internal_note";
  to: string;
  subject: string;
  body: string;
}

export interface Analysis {
  headline: string;
  explanation: string;
  recommended_action: string;
  drafts: Draft[];
}

export interface Route {
  action: "auto_post" | "needs_approval";
  approver: string | null;
  reasons: string[];
  recommendation: "approve" | "reject" | "resolve_first" | null;
}

export interface Pending {
  approver: string;
  recommendation: Route["recommendation"];
  reasons: string[];
  headline: string | null;
}

export interface PostOutcome {
  status: "posted";
  document_number: string;
  due_date: string;
  amount: string;
  approved_by: string;
  note: string | null;
}

export interface RejectOutcome {
  status: "rejected";
  rejected_by: string;
  note: string | null;
  amount: string;
}

export type RunOutcome = PostOutcome | RejectOutcome;

export interface Run {
  doc_id: string;
  file: string;
  received_date: string;
  recorded_at: string;
  model: string;
  status: RunStatus;
  state: {
    extraction: Extraction | null;
    invoice: Invoice | null;
    match: Match | null;
    analysis: Analysis | null;
    route: Route | null;
    decision: { decision: string; note: string | null; reviewer: string | null } | null;
    outcome: RunOutcome | null;
    errors: string[] | null;
  };
  pending: Pending | null;
  steps: Step[];
  metrics: { automated_ms: number; llm_ms: number; cost_usd: number; input_tokens: number; output_tokens: number };
}

export interface Summary {
  invoices: number;
  model: string;
  statuses: Record<string, number>;
  touchless: number;
  exceptions_match_answer_key: number;
  extraction: {
    fields_total: number;
    fields_correct: number;
    field_accuracy: number;
    invoices_total: number;
    invoices_all_correct: number;
  };
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
}

export interface Preview {
  outcome: RunOutcome;
  step: Step;
}

export interface Batch {
  summary: Summary;
  roles: string[];
  auto_post_limit: string;
  exception_labels: Record<string, { label: string; owner: string }>;
  runs: Run[];
  decision_previews: Record<string, { approve: Preview; reject: Preview }>;
}

export interface Decision {
  decision: "approve" | "reject";
  note: string;
  reviewer: string;
  decidedAt: string;
}
