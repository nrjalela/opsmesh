"""Live mode: an invoice submitted as a GitHub issue goes through the same LangGraph
pipeline as the recorded demo. This module decides WHAT should happen; the workflow
just applies the result (comment, labels, close) with the GitHub CLI.

Order of checks for a new invoice, cheapest first so rejections never cost API credit:
  author -> PDF link -> download -> PDF hash duplicate -> daily cap -> Claude
"""

from __future__ import annotations

import hashlib
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

import opsmesh.agents.graph as graph_mod
from opsmesh.engine.models import LedgerLine, PostedInvoice
from opsmesh.live import render
from opsmesh.live.issue import PDFError, download_pdf, find_pdf_url, parse_command
from opsmesh.live.state import StateStore, local_date

OWNER = "nrjalela"
DAILY_CAP = 5
LABELS = ("posted", "held", "rejected", "duplicate", "over-cap")


@dataclass
class Outcome:
    status: str  # posted | held | rejected | duplicate | over-cap | ignored | error | noop
    comment: str | None = None
    add_labels: list[str] = field(default_factory=list)
    close: bool = False

    @property
    def remove_labels(self) -> list[str]:
        return [label for label in LABELS if label not in self.add_labels]


def doc_id(issue: int) -> str:
    return f"GH-{issue:04d}"


def _graph(store: StateStore):
    return graph_mod.build_graph(checkpointer=SqliteSaver(store.connect()))


def process_issue(*, issue: int, author: str, body: str, created_at: str, store: StateStore,
                  now: datetime | None = None, fetch: Callable[[str], bytes] = download_pdf,
                  run_url: str | None = None, cap: int = DAILY_CAP, owner: str = OWNER) -> Outcome:
    now = now or datetime.now(timezone.utc)
    if author != owner:  # the workflow already filters; this is the second lock on the door
        return Outcome("ignored")
    if store.has_run(issue):
        return Outcome("noop", render.simple_comment(issue, "noop", "Already processed",
                       "This issue already has a run. Use `/approve` or `/reject` if it's held."))

    url = find_pdf_url(body)
    if url is None:
        return Outcome("error", render.simple_comment(issue, "error", "⚠️ No PDF found",
                       "Attach the invoice PDF with the form's upload field, then comment `/retry`."))
    try:
        pdf = fetch(url)
    except PDFError as e:
        return Outcome("error", render.simple_comment(issue, "error", "⚠️ Couldn't use the attachment",
                       f"{e} Fix the attachment, then comment `/retry`."))

    sha = hashlib.sha256(pdf).hexdigest()
    first = store.hash_owner(sha)
    if first is not None and first != issue:
        store.audit("duplicate", issue, now, sha256=sha, original_issue=first)
        return Outcome("duplicate", render.simple_comment(issue, "duplicate", "🔁 Duplicate PDF",
                       f"This exact file (SHA-256 `{sha[:12]}…`) was already submitted in #{first}. "
                       "Nothing was processed and no API credit was spent."), ["duplicate"], close=True)

    today = local_date(now)
    if store.processed_on(today) >= cap:
        store.audit("deferred", issue, now, sha256=sha, reason="daily cap")
        return Outcome("over-cap", render.simple_comment(issue, "over-cap", "⏳ Daily cap reached",
                       f"Live mode processes at most {cap} invoices per day (Australian time) to keep API "
                       "spend predictable. Comment `/retry` tomorrow to process this one."), ["over-cap"])

    graph_mod.use_master(store.master())
    try:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"{doc_id(issue)}.pdf"
            path.write_bytes(pdf)
            graph = _graph(store)
            state = graph_mod.start_run(graph, doc_id(issue), path, created_at[:10])
    finally:
        graph_mod.use_master(None)

    store.record_hash(sha, issue)
    status = "held" if state.get("pending") else (state.get("outcome") or {}).get("status", "error")
    cost = round(sum(s.get("cost_usd", 0) for s in state.get("steps") or []), 6)
    store.audit("processed", issue, now, sha256=sha, status=status, cost_usd=cost,
                exceptions=[e["type"] for e in (state.get("match") or {}).get("exceptions") or []])
    if status == "posted":
        _post_to_ledger(store, state, now)
    comment = render.result_comment(issue, state, run_url)
    return Outcome(status, comment, [status] if status in LABELS else [], close=status == "posted")


def handle_comment(*, issue: int, author: str, comment_body: str, issue_body: str, created_at: str,
                   store: StateStore, now: datetime | None = None,
                   fetch: Callable[[str], bytes] = download_pdf, run_url: str | None = None,
                   cap: int = DAILY_CAP, owner: str = OWNER) -> Outcome:
    now = now or datetime.now(timezone.utc)
    cmd = parse_command(comment_body)
    if cmd is None or author != owner:
        return Outcome("ignored")
    if cmd.action == "retry":
        if store.has_run(issue):
            return Outcome("noop", render.simple_comment(issue, "noop", "Nothing to retry",
                           "This invoice has already been processed."))
        return process_issue(issue=issue, author=author, body=issue_body, created_at=created_at, store=store,
                             now=now, fetch=fetch, run_url=run_url, cap=cap, owner=owner)

    graph = _graph(store)
    current = graph_mod.graph_state(graph, doc_id(issue))
    if not current.get("pending"):
        return Outcome("noop", render.simple_comment(issue, "noop", "Nothing waiting for a decision",
                       "This invoice isn't held (it may already be decided). Decisions only count once."))

    approver_role = current["pending"]["approver"]
    decision = {"decision": cmd.action, "note": cmd.note, "reviewer": f"@{author} ({approver_role})"}
    graph_mod.use_master(store.master())
    try:
        state = graph_mod.resume_run(graph, doc_id(issue), decision)
    finally:
        graph_mod.use_master(None)

    status = (state.get("outcome") or {}).get("status", "error")
    # One person both submits and approves in this demo, so segregation of duties can't be enforced; say so.
    store.audit("decided", issue, now, actor=author, decision=cmd.action, note=cmd.note, role=approver_role,
                status=status, same_person_as_submitter=True)
    if status == "posted":
        _post_to_ledger(store, state, now)
    return Outcome(status, render.decision_comment(issue, state, author, cmd.note, run_url),
                   [status] if status in LABELS else [], close=True)


def _post_to_ledger(store: StateStore, state: dict, now: datetime) -> None:
    """Posted live invoices join the AP ledger, so resubmitting one is caught as a duplicate."""
    inv, match, outcome = state.get("invoice") or {}, state.get("match") or {}, state.get("outcome") or {}
    if not match.get("vendor_id"):
        return  # an unknown vendor approved by a person: nothing to key a duplicate check on
    store.add_to_ledger(PostedInvoice(
        document_number=outcome["document_number"], vendor_id=match["vendor_id"],
        invoice_number=inv["invoice_number"], invoice_date=date.fromisoformat(inv["invoice_date"]),
        posted_date=now.date(), po_number=match.get("po_number"), total=Decimal(inv["total"]),
        lines=[LedgerLine(po_line=ln["po_line"], quantity=Decimal(ln["invoiced_qty"]))
               for ln in match.get("lines") or [] if ln.get("po_line")],
    ))
