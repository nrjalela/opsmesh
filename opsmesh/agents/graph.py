"""The AP workflow as a LangGraph state machine.

    intake (LLM) -> validate (code) -> match (code) -> [explain (LLM)] -> route (code)
        -> auto-post                                   -> post
        -> needs approval -> human_review (interrupt)  -> post | reject

State is kept JSON-serialisable (plain dicts) so a finished or paused run can
be written straight to a replay file.
"""

from __future__ import annotations

import operator
from datetime import date, datetime, timezone
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, TypedDict

import anthropic
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from opsmesh.agents.exceptions import ExceptionAnalysis, run_exception_agent
from opsmesh.agents.intake import run_intake
from opsmesh.agents.llm import LLMRefusal
from opsmesh.agents.router import RouteDecision, load_rules, route_invoice
from opsmesh.agents.schema import (
    InvoiceExtraction, ValidationReport, field_confidences, to_invoice_document, validate_extraction,
)
from opsmesh.agents.steps import StepLog, Timer, now_iso
from opsmesh.config import MASTER_DIR, load_tolerances
from opsmesh.engine.master import MasterData
from opsmesh.engine.matching import MatchResult, TraceStep, match_invoice
from opsmesh.engine.models import InvoiceDocument
from opsmesh.engine.money import aud
from opsmesh.engine.terms import due_date


class APState(TypedDict, total=False):
    doc_id: str
    pdf_path: str
    received_date: str
    extraction: dict | None
    validation: dict | None
    invoice: dict | None
    match: dict | None
    analysis: dict | None
    draft_requests: list[dict]
    route: dict | None
    decision: dict | None
    outcome: dict | None
    errors: Annotated[list[str], operator.add]
    steps: Annotated[list[dict], operator.add]


@lru_cache
def get_master() -> MasterData:
    return MasterData.load(MASTER_DIR)


def _step(**kw: Any) -> list[dict]:
    return [StepLog(**kw).model_dump(mode="json")]


def _llm_step(node: str, title: str, timer: Timer, summary: str, result, rationale: str) -> list[dict]:
    # Adaptive thinking often skips thinking on routine documents; fall back to the
    # model's own stated rationale from its structured output.
    reasoning = result.thinking_summary or rationale
    return _step(node=node, title=title, kind="llm", started_at=timer.started_at, duration_ms=timer.ms,
                 summary=summary, reasoning=reasoning, model=result.model,
                 input_tokens=result.input_tokens, output_tokens=result.output_tokens, cost_usd=result.cost_usd)


def _error_text(e: Exception) -> str:
    if isinstance(e, LLMRefusal):
        return str(e)
    if isinstance(e, anthropic.APIError):
        return f"Claude API error ({type(e).__name__})"
    return f"{type(e).__name__}: {e}"


# --- nodes ------------------------------------------------------------------------------

def intake_node(state: APState) -> dict:
    timer = Timer()
    try:
        result = run_intake(Path(state["pdf_path"]), state.get("received_date"))
    except Exception as e:  # the invoice still has to go somewhere: a person
        err = _error_text(e)
        return {"extraction": None, "errors": [f"Intake: {err}"],
                "steps": _step(node="intake", title="Intake agent read the PDF", kind="llm", started_at=timer.started_at,
                               duration_ms=timer.ms, summary="Couldn't extract the invoice.", error=err)}
    x = result.output
    n = len(x.lines)
    summary = (f"Read {x.vendor_name.value or 'unknown vendor'} invoice {x.invoice_number.value or '?'}: "
               f"{n} line{'s' if n != 1 else ''}, total {x.total_inc_gst.value}.")
    confs = sorted(field_confidences(x).items(), key=lambda kv: kv[1])[:3]
    rationale = (x.notes_for_ap or "Nothing unusual noted on the document.") + " Least certain fields: " + \
        ", ".join(f"{k} ({c:.0%})" for k, c in confs) + "."
    return {"extraction": x.model_dump(mode="json"),
            "steps": _llm_step("intake", "Intake agent read the PDF", timer, summary, result, rationale)}


def validate_node(state: APState) -> dict:
    timer = Timer()
    if not state.get("extraction"):
        return {"validation": None, "invoice": None,
                "steps": _step(node="validate", title="Checked the extraction", kind="code", started_at=timer.started_at,
                               duration_ms=timer.ms, summary="Skipped: nothing was extracted.")}
    x = InvoiceExtraction.model_validate(state["extraction"])
    received = date.fromisoformat(state["received_date"]) if state.get("received_date") else None
    report = validate_extraction(x, load_rules().min_field_confidence, received)
    doc = to_invoice_document(x)
    fails = [c for c in report.checks if c.outcome == "fail"]
    summary = "All extraction checks passed." if not fails else f"{len(fails)} check(s) flagged: " + "; ".join(c.check for c in fails) + "."
    return {"validation": report.model_dump(mode="json"),
            "invoice": doc.model_dump(mode="json") if doc else None,
            "steps": _step(node="validate", title="Checked the extraction", kind="code", started_at=timer.started_at,
                           duration_ms=timer.ms, summary=summary, trace=report.checks,
                           reasoning="ABN checksum, arithmetic cross-checks and per-field confidence, in code.")}


def match_node(state: APState) -> dict:
    timer = Timer()
    if not state.get("invoice"):
        return {"match": None,
                "steps": _step(node="match", title="Three-way match", kind="code", started_at=timer.started_at,
                               duration_ms=timer.ms, summary="Skipped: required fields missing, so there is nothing to match.")}
    inv = InvoiceDocument.model_validate(state["invoice"])
    result = match_invoice(inv, get_master(), load_tolerances())
    return {"match": result.model_dump(mode="json"),
            "steps": _step(node="match", title="Three-way match", kind="code", started_at=timer.started_at,
                           duration_ms=timer.ms, summary=result.summary, trace=result.trace,
                           reasoning="Deterministic rules: vendor master, AP ledger, PO, goods receipts and GST, "
                                     "with the tolerances in config/tolerances.yaml.")}


def explain_node(state: APState) -> dict:
    timer = Timer()
    match = MatchResult.model_validate(state["match"])
    inv = InvoiceDocument.model_validate(state["invoice"])
    try:
        result, requests = run_exception_agent(match, inv, get_master())
    except Exception as e:
        err = _error_text(e)
        return {"analysis": None, "errors": [f"Exception agent: {err}"],
                "steps": _step(node="explain", title="Exception agent explained the problem", kind="llm",
                               started_at=timer.started_at, duration_ms=timer.ms,
                               summary="Couldn't draft the explanation; the engine's findings still stand.", error=err)}
    a = result.output
    return {"analysis": a.model_dump(mode="json"), "draft_requests": [r.__dict__ for r in requests],
            "steps": _llm_step("explain", "Exception agent explained the problem", timer,
                               f"{a.headline} Drafted {len(a.drafts)} message(s).", result,
                               f"{a.explanation} Recommended: {a.recommended_action}")}


def route_node(state: APState) -> dict:
    timer = Timer()
    match = MatchResult.model_validate(state["match"]) if state.get("match") else None
    validation = ValidationReport.model_validate(state["validation"]) if state.get("validation") else None
    total = Decimal(state["invoice"]["total"]) if state.get("invoice") else None
    decision = route_invoice(
        match, total,
        low_confidence=validation.low_confidence if validation else [],
        missing=validation.missing if validation else ["the whole document"],
        errors=state.get("errors", []),
    )
    if decision.action == "auto_post":
        summary = "Auto-post: no human needed."
    else:
        summary = f"Needs approval from the {decision.approver}."
    route = decision.model_dump(mode="json") | {"decided_at": now_iso()}
    return {"route": route,
            "steps": _step(node="route", title="Approval router", kind="code", started_at=timer.started_at,
                           duration_ms=timer.ms, summary=summary,
                           trace=[TraceStep(check="Rule", outcome="info", detail=r) for r in decision.reasons],
                           reasoning="Rules in config/approval_rules.yaml: auto-post limit, amount tiers, "
                                     "exception reviewers and confidence threshold.")}


def approval_request(state: APState) -> dict:
    inv = state.get("invoice") or {}
    route = state["route"]
    return {
        "doc_id": state["doc_id"],
        "approver": route["approver"],
        "recommendation": route["recommendation"],
        "reasons": route["reasons"],
        "vendor": inv.get("vendor_name"),
        "invoice_number": inv.get("invoice_number"),
        "total": inv.get("total"),
        "headline": (state.get("analysis") or {}).get("headline"),
    }


def human_review_node(state: APState) -> dict:
    # Pauses the graph. Resumes with {"decision": "approve"|"reject", "note": str, "reviewer": str}.
    decision = interrupt(approval_request(state))
    return {"decision": decision, "steps": decision_step(state, decision)}


def decision_step(state: APState, decision: dict) -> list[dict]:
    decided = datetime.now(timezone.utc)
    paused = datetime.fromisoformat(state["route"]["decided_at"])
    verb = "Approved" if decision["decision"] == "approve" else "Rejected"
    note = decision.get("note") or ""
    return _step(node="human_review", title="Human approval", kind="human", started_at=state["route"]["decided_at"],
                 duration_ms=int((decided - paused).total_seconds() * 1000),
                 summary=f"{verb} by {decision.get('reviewer') or state['route']['approver']}." + (f' "{note}"' if note else ""),
                 reasoning=note)


def post_node(state: APState) -> dict:
    return finalise(state, "post")


def reject_node(state: APState) -> dict:
    return finalise(state, "reject")


def finalise(state: APState, action: str) -> dict:
    """Post or reject. Pure code, shared by the live graph and replay mode."""
    timer = Timer()
    inv = state.get("invoice") or {}
    decision = state.get("decision")
    if action == "post":
        vendor = get_master().vendor((state.get("match") or {}).get("vendor_id") or "")
        inv_date = date.fromisoformat(inv["invoice_date"])
        due = due_date(inv_date, vendor.payment_terms) if vendor else inv_date
        doc_no = f"51059{int(state['doc_id'].split('-')[1]):05d}"
        by = "Rules (touchless)" if not decision else decision.get("reviewer") or state["route"]["approver"]
        outcome = {"status": "posted", "document_number": doc_no, "due_date": due.isoformat(),
                   "amount": inv.get("total"), "approved_by": by, "note": (decision or {}).get("note")}
        summary = f"Posted as document {doc_no}; {aud(Decimal(inv['total']))} scheduled for payment on {due:%-d %b %Y}."
        title = "Posted to the ledger"
    else:
        outcome = {"status": "rejected", "rejected_by": decision.get("reviewer") or state["route"]["approver"],
                   "note": decision.get("note"), "amount": inv.get("total")}
        summary = "Rejected: not posted. " + ("Follow-up drafts are ready to send." if state.get("analysis") else "")
        title = "Rejected"
    return {"outcome": outcome,
            "steps": _step(node=action, title=title, kind="code", started_at=timer.started_at,
                           duration_ms=timer.ms, summary=summary.strip())}


# --- edges ------------------------------------------------------------------------------

def after_match(state: APState) -> str:
    m = state.get("match")
    return "explain" if m and m.get("exceptions") else "route"


def after_route(state: APState) -> str:
    return "post" if state["route"]["action"] == "auto_post" else "human_review"


def after_review(state: APState) -> str:
    return "post" if state["decision"]["decision"] == "approve" else "reject"


def build_graph(checkpointer=None):
    g = StateGraph(APState)
    g.add_node("intake", intake_node)
    g.add_node("validate", validate_node)
    g.add_node("match", match_node)
    g.add_node("explain", explain_node)
    g.add_node("route", route_node)
    g.add_node("human_review", human_review_node)
    g.add_node("post", post_node)
    g.add_node("reject", reject_node)
    g.add_edge(START, "intake")
    g.add_edge("intake", "validate")
    g.add_edge("validate", "match")
    g.add_conditional_edges("match", after_match, ["explain", "route"])
    g.add_edge("explain", "route")
    g.add_conditional_edges("route", after_route, ["post", "human_review"])
    g.add_conditional_edges("human_review", after_review, ["post", "reject"])
    g.add_edge("post", END)
    g.add_edge("reject", END)
    return g.compile(checkpointer=checkpointer or InMemorySaver())


def start_run(graph, doc_id: str, pdf_path: Path, received_date: str | None) -> dict:
    """Run until the graph finishes or pauses for approval. Returns the state."""
    config = {"configurable": {"thread_id": doc_id}}
    graph.invoke({"doc_id": doc_id, "pdf_path": str(pdf_path), "received_date": received_date,
                  "errors": [], "steps": []}, config)
    return graph_state(graph, doc_id)


def resume_run(graph, doc_id: str, decision: dict) -> dict:
    graph.invoke(Command(resume=decision), {"configurable": {"thread_id": doc_id}})
    return graph_state(graph, doc_id)


def graph_state(graph, doc_id: str) -> dict:
    snap = graph.get_state({"configurable": {"thread_id": doc_id}})
    state = {k: None for k in APState.__annotations__} | dict(snap.values)
    state["pending"] = snap.interrupts[0].value if snap.interrupts else None
    return state
