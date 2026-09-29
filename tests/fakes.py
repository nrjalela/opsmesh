"""Stand-ins for the two Claude calls, so the whole graph can be tested offline."""

from __future__ import annotations

from opsmesh.agents.exceptions import Draft, ExceptionAnalysis, plan_drafts
from opsmesh.agents.llm import LLMResult
from opsmesh.agents.schema import InvoiceExtraction


def extraction_from_truth(truth: dict, confidence: float = 0.98) -> InvoiceExtraction:
    def t(v):
        return {"value": v, "confidence": confidence}

    def n(v):
        return {"value": float(v) if v is not None else None, "confidence": confidence}

    return InvoiceExtraction.model_validate({
        "is_tax_invoice": True,
        "vendor_name": t(truth["vendor_name"]),
        "vendor_abn": t(truth["vendor_abn"]),
        "invoice_number": t(truth["invoice_number"]),
        "invoice_date": t(truth["invoice_date"]),
        "due_date": t(None),
        "po_number": t(truth["po_number"]),
        "currency": t("AUD"),
        "lines": [{
            "description": t(ln["description"]), "item_code": t(ln["item_code"]),
            "po_line": {"value": ln["po_line"], "confidence": confidence},
            "quantity": n(ln["quantity"]), "uom": t(ln["uom"]), "unit_price": n(ln["unit_price"]),
            "amount": n(ln["amount"]), "gst_applicable": {"value": ln["gst_applicable"], "confidence": confidence},
        } for ln in truth["lines"]],
        "subtotal_ex_gst": n(truth["subtotal"]),
        "gst_amount": n(truth["gst_amount"]),
        "total_inc_gst": n(truth["total"]),
        "remarks": t(truth["remarks"]),
        "notes_for_ap": "",
    })


def fake_result(output) -> LLMResult:
    return LLMResult(output=output, model="fake", input_tokens=100, output_tokens=50, cache_read_tokens=0,
                     cost_usd=0.001, duration_ms=5, thinking_summary="(stubbed)", request_id=None)


def fake_exception_agent(match, inv, master):
    requests = plan_drafts(match, inv, master)
    analysis = ExceptionAnalysis(
        headline="stub headline", explanation="stub", recommended_action="stub",
        drafts=[Draft(kind="internal_note", to="whoever the model says", subject="s", body="b") for _ in requests],
    )
    return fake_result(analysis), requests
