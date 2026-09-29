"""The LangGraph workflow end to end, with the two Claude calls stubbed.

Real graph, real validation, real engine, real router, real interrupt/resume.
Only the model is faked (from the answer key), so this runs free in CI.
"""

from __future__ import annotations

import json
from decimal import Decimal as D

import pytest

import opsmesh.agents.graph as graph_mod
from opsmesh.agents.exceptions import plan_drafts
from opsmesh.agents.llm import LLMRefusal
from opsmesh.agents.router import load_rules, route_invoice
from opsmesh.agents.schema import to_invoice_document, validate_extraction
from opsmesh.config import DATA_DIR, INVOICE_DIR, load_tolerances
from opsmesh.engine.matching import match_invoice
from opsmesh.engine.models import InvoiceDocument
from opsmesh.replay.accuracy import score_invoice, summarise
from opsmesh.replay.store import apply_decision, build_replay
from tests.fakes import extraction_from_truth, fake_exception_agent, fake_result

KEY = json.loads((DATA_DIR / "answer_key.json").read_text())
INDEX = {i["doc_id"]: i for i in json.loads((INVOICE_DIR / "index.json").read_text())}
BY_SCENARIO = {v["scenario"]: d for d, v in KEY.items()}


def expected_route(entry: dict) -> tuple[str, str | None]:
    """The approval matrix, written out independently of the router code."""
    s, cat = entry["scenario"], entry["category"]
    if cat in ("clean", "within_tolerance"):
        return "auto_post", None
    if s in ("H01", "H03"):
        return "needs_approval", "AP Supervisor"
    if s == "H02":
        return "needs_approval", "Finance Manager"
    if cat == "unknown_vendor":
        return "needs_approval", "AP Supervisor"
    return "needs_approval", "AP Officer"


@pytest.fixture
def stub_llm(monkeypatch):
    by_pdf = {str(INVOICE_DIR / INDEX[d]["file"]): KEY[d]["invoice"] for d in KEY}
    monkeypatch.setattr(graph_mod, "run_intake", lambda path, received=None: fake_result(extraction_from_truth(by_pdf[str(path)])))
    monkeypatch.setattr(graph_mod, "run_exception_agent", fake_exception_agent)


def run(doc_id: str, graph=None):
    graph = graph or graph_mod.build_graph()
    item = INDEX[doc_id]
    return graph, graph_mod.start_run(graph, doc_id, INVOICE_DIR / item["file"], item["received_date"])


@pytest.mark.parametrize("doc_id", sorted(KEY))
def test_every_invoice_routes_as_the_approval_matrix_says(stub_llm, doc_id):
    _, state = run(doc_id)
    entry = KEY[doc_id]
    got_types = sorted({e["type"] for e in state["match"]["exceptions"]})
    assert got_types == sorted(entry["expected_exceptions"])
    action, approver = expected_route(entry)
    assert state["route"]["action"] == action
    assert state["route"]["approver"] == approver
    nodes = [s["node"] for s in state["steps"]]
    if action == "auto_post":
        assert state["pending"] is None and state["outcome"]["status"] == "posted"
        assert nodes == ["intake", "validate", "match", "route", "post"]
    else:
        assert state["pending"]["approver"] == approver
        assert state["outcome"] is None
        assert nodes[-1] == "route"
        assert ("explain" in nodes) == bool(entry["expected_exceptions"])
    for s in state["steps"]:
        assert s["duration_ms"] >= 0 and s["summary"]


def test_touchless_count(stub_llm):
    touchless = sum(expected_route(e)[0] == "auto_post" for e in KEY.values())
    assert touchless == 21


def test_approve_resumes_to_posting(stub_llm):
    doc = BY_SCENARIO["H02"]
    graph, state = run(doc)
    assert state["pending"]["approver"] == "Finance Manager"
    state = graph_mod.resume_run(graph, doc, {"decision": "approve", "note": "Mould signed off by plant manager", "reviewer": "Finance Manager"})
    assert state["pending"] is None
    assert state["outcome"]["status"] == "posted"
    assert state["outcome"]["approved_by"] == "Finance Manager"
    assert [s["node"] for s in state["steps"]][-2:] == ["human_review", "post"]


def test_reject_duplicate(stub_llm):
    doc = BY_SCENARIO["D01"]
    graph, state = run(doc)
    assert state["route"]["recommendation"] == "reject"
    state = graph_mod.resume_run(graph, doc, {"decision": "reject", "note": "Already paid", "reviewer": "AP Officer"})
    assert state["outcome"]["status"] == "rejected"


def test_low_confidence_extraction_goes_to_a_person(monkeypatch):
    doc = BY_SCENARIO["C01"]
    x = extraction_from_truth(KEY[doc]["invoice"])
    x.total_inc_gst.confidence = 0.55
    monkeypatch.setattr(graph_mod, "run_intake", lambda path, received=None: fake_result(x))
    _, state = run(doc)
    assert state["match"]["exceptions"] == []
    assert state["route"]["action"] == "needs_approval"
    assert "total_inc_gst" in " ".join(state["route"]["reasons"])


def test_model_refusal_is_routed_not_crashed(monkeypatch):
    def refuse(path, received=None):
        raise LLMRefusal("Model declined (category: general_harms)")
    monkeypatch.setattr(graph_mod, "run_intake", refuse)
    _, state = run(BY_SCENARIO["C01"])
    assert state["route"]["action"] == "needs_approval"
    assert any("declined" in r for r in state["route"]["reasons"])
    assert state["steps"][0]["error"]


def test_replay_decision_uses_same_posting_code(stub_llm):
    doc = BY_SCENARIO["P01"]
    _, state = run(doc)
    replay = build_replay(state, file=INDEX[doc]["file"], model="fake")
    assert replay["status"] == "awaiting_approval"
    done = apply_decision(replay, {"decision": "approve", "note": "Buyer confirmed new ink price", "reviewer": "AP Officer"})
    assert done["status"] == "posted" and done["pending"] is None
    assert [s["node"] for s in done["steps"]][-2:] == ["human_review", "post"]
    assert replay["status"] == "awaiting_approval"  # original untouched


# --- pieces --------------------------------------------------------------------------------

def test_ground_truth_extraction_round_trips():
    for doc, entry in KEY.items():
        x = extraction_from_truth(entry["invoice"])
        report = validate_extraction(x, 0.8)
        truth = InvoiceDocument.model_validate(entry["invoice"])
        assert to_invoice_document(x) == truth, doc
        math_ok = not any(c.outcome == "fail" and c.check != "ABN checksum" for c in report.checks)
        assert math_ok, doc


def test_validation_flags_bad_arithmetic_and_abn():
    x = extraction_from_truth(KEY[BY_SCENARIO["C02"]]["invoice"])
    x.total_inc_gst.value += 100
    x.vendor_abn.value = "12345678901"
    fails = {c.check for c in validate_extraction(x, 0.8).checks if c.outcome == "fail"}
    assert fails == {"ABN checksum", "Subtotal + GST = total"}


def test_lookalike_vendor_never_gets_an_email():
    doc = BY_SCENARIO["U02"]
    inv = InvoiceDocument.model_validate(KEY[doc]["invoice"])
    master = graph_mod.get_master()
    reqs = plan_drafts(match_invoice(inv, master, load_tolerances()), inv, master)
    assert [(r.kind, r.to) for r in reqs] == [("internal_note", "Vendor master team")]
    assert "otway-adhesives-au" not in json.dumps([r.__dict__ for r in reqs])


def test_multi_exception_drafts_split_by_audience():
    doc = BY_SCENARIO["X01"]
    inv = InvoiceDocument.model_validate(KEY[doc]["invoice"])
    master = graph_mod.get_master()
    reqs = plan_drafts(match_invoice(inv, master, load_tolerances()), inv, master)
    kinds = sorted(r.kind for r in reqs)
    assert kinds == ["internal_note", "vendor_email"]
    email = next(r for r in reqs if r.kind == "vendor_email")
    assert master.vendor("V1008").email in email.to  # the address on file


def test_exception_agent_cannot_change_recipients(monkeypatch):
    doc = BY_SCENARIO["S01"]
    monkeypatch.setattr(graph_mod, "run_intake", lambda p, r=None: fake_result(extraction_from_truth(KEY[doc]["invoice"])))
    from opsmesh.agents import exceptions as ex_mod

    captured = {}

    def fake_call(**kw):
        from opsmesh.agents.exceptions import Draft, ExceptionAnalysis
        out = ExceptionAnalysis(headline="h", explanation="e", recommended_action="r",
                                drafts=[Draft(kind="internal_note", to="attacker@evil.example", subject="s", body="b")])
        captured["called"] = True
        return fake_result(out)

    monkeypatch.setattr(ex_mod, "structured_call", fake_call)
    _, state = run(doc)
    draft = state["analysis"]["drafts"][0]
    assert captured["called"]
    assert draft["kind"] == "vendor_email"
    assert "evil" not in draft["to"] and "mooraboolpallets.example" in draft["to"]


@pytest.mark.parametrize("total,action,approver", [
    ("20000.00", "auto_post", None),
    ("20000.01", "needs_approval", "AP Supervisor"),
    ("100000.00", "needs_approval", "AP Supervisor"),
    ("100000.01", "needs_approval", "Finance Manager"),
])
def test_amount_thresholds(total, action, approver):
    inv = InvoiceDocument.model_validate(KEY[BY_SCENARIO["C01"]]["invoice"])
    match = match_invoice(inv, graph_mod.get_master(), load_tolerances())
    d = route_invoice(match, D(total), [], [], [], load_rules())
    assert (d.action, d.approver) == (action, approver)


def test_held_invoice_over_limit_escalates():
    inv = InvoiceDocument.model_validate(KEY[BY_SCENARIO["P02"]]["invoice"])
    match = match_invoice(inv, graph_mod.get_master(), load_tolerances())
    assert route_invoice(match, D("150000"), [], [], [], load_rules()).approver == "Finance Manager"


def test_accuracy_scoring():
    truth = KEY[BY_SCENARIO["X01"]]["invoice"]
    perfect = extraction_from_truth(truth).model_dump(mode="json")
    rows = score_invoice(perfect, truth)
    assert all(r["correct"] for r in rows)
    perfect["lines"][0]["unit_price"]["value"] = 15.09
    perfect["invoice_number"]["value"] = perfect["invoice_number"]["value"].lower()  # case is not an error
    s = summarise({"X": score_invoice(perfect, truth)})
    assert s["fields_total"] == len(rows)
    assert s["fields_correct"] == len(rows) - 1
    assert score_invoice(None, truth)[0]["correct"] is False
