"""Exception agent: explain a failed match in plain English and draft the follow-up.

Code decides WHO needs to hear about each exception (vendor, buyer, receiving,
vendor master). The model decides HOW to say it. That keeps a suspected
impersonator's email address out of the To: line no matter what the model
writes, and it keeps the facts coming from the engine, not the model.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Literal

from pydantic import BaseModel, Field

from opsmesh.agents.llm import LLMResult, structured_call
from opsmesh.engine.master import MasterData
from opsmesh.engine.matching import ExceptionType as E
from opsmesh.engine.matching import MatchResult
from opsmesh.engine.models import InvoiceDocument
from opsmesh.engine.money import aud
from opsmesh.engine.terms import due_date

DraftKind = Literal["vendor_email", "internal_note"]


class Draft(BaseModel):
    kind: DraftKind
    to: str
    subject: str
    body: str = Field(description="Plain text with line breaks, no markdown")


class ExceptionAnalysis(BaseModel):
    headline: str = Field(description="One plain-English sentence: what's wrong and the dollar value at stake")
    explanation: str = Field(description="Two to four sentences an AP officer can read in ten seconds")
    recommended_action: str = Field(description="What the approver should do now, in one or two sentences")
    drafts: list[Draft] = Field(description="Exactly one per draft request, in the same order, using the given kind and to")


@dataclass
class DraftRequest:
    kind: DraftKind
    to: str
    purpose: str
    exception_types: list[str]


RECEIVING = "Receiving team, Corio plant"
VENDOR_MASTER = "Vendor master team"


def plan_drafts(match: MatchResult, inv: InvoiceDocument, master: MasterData) -> list[DraftRequest]:
    vendor = master.vendor(match.vendor_id) if match.vendor_id else None
    po = master.po(match.po_number)
    buyer = f"{po.buyer} (Procurement, buyer on PO {po.po_number})" if po else "Procurement team"
    vendor_to = f"{vendor.name} <{vendor.email}>" if vendor else None  # always the address ON FILE

    reqs: dict[tuple[str, str], DraftRequest] = {}

    def add(kind: DraftKind, to: str | None, purpose: str, t: E) -> None:
        if to is None:
            return
        key = (kind, to)
        if key in reqs:
            reqs[key].purpose += " " + purpose
            reqs[key].exception_types.append(t.value)
        else:
            reqs[key] = DraftRequest(kind, to, purpose, [t.value])

    for exc in match.exceptions:
        t = exc.type
        if t is E.PRICE_VARIANCE:
            add("internal_note", buyer, "Ask the buyer whether the higher price was agreed. If yes, they amend the PO "
                "price so the invoice can be released; if not, AP will ask the vendor for a credit note for the difference.", t)
        elif t is E.SHORT_SHIPPED:
            add("vendor_email", vendor_to, "Tell the vendor we received fewer units than they billed and ask for a credit "
                "note for the shortfall. We'll pay for what was received once that's sorted.", t)
        elif t is E.DUPLICATE_INVOICE:
            posted = next((p for p in master.ledger if p.document_number == exc.details.get("posted_document")), None)
            when = due_date(posted.invoice_date, vendor.payment_terms).strftime("%-d %B %Y") if posted and vendor else None
            add("vendor_email", vendor_to, "Let the vendor know this invoice is already in our system and won't be paid "
                f"twice{f'; it is due for payment on {when}' if when else ''}. No action needed from them; please don't resend.", t)
        elif t is E.MISSING_GOODS_RECEIPT:
            add("internal_note", RECEIVING, "Ask receiving to confirm whether these goods arrived and, if so, post the "
                "goods receipt so the invoice can be paid. If they haven't arrived, say so and AP will query the vendor.", t)
        elif t is E.UNKNOWN_VENDOR:
            if exc.details.get("lookalike_vendor"):
                add("internal_note", VENDOR_MASTER, "Possible impersonation of an existing vendor: the name matches a vendor "
                    "on file but the ABN doesn't, and the invoice asks for payment to new bank details. Do not pay and do "
                    "not change any bank details. Verify by phone using the contact details already on file.", t)
            else:
                add("internal_note", VENDOR_MASTER, "A supplier with no vendor record and no PO has invoiced us. Find out "
                    "who engaged them, then onboard properly (ABN check, verified bank details) and get a PO or non-PO "
                    "approval before anything is paid.", t)
        elif t is E.GST_ERROR:
            add("vendor_email", vendor_to, "Ask the vendor for a corrected tax invoice, stating the GST we expected and why.", t)
        elif t is E.INVOICE_MATH:
            add("vendor_email", vendor_to, "Ask the vendor for a corrected invoice; the figures on it don't add up.", t)
        else:  # PO problems: the buyer owns the PO
            add("internal_note", buyer, "Ask the buyer to sort out the PO so this invoice can be matched.", t)
    return list(reqs.values())


SYSTEM = """You write up invoice exceptions for the accounts payable team at Corio Packaging Pty Ltd, a packaging manufacturer in Geelong, Australia.

A deterministic matching engine has already compared the invoice with the purchase order, goods receipts and AP ledger. Its findings are facts. Don't recompute, dispute or add to them, and don't introduce figures that aren't in the findings.

Drafts: write exactly one per request, in order, keeping the given kind and to.
- Vendor emails: courteous, factual and never accusatory. Quote the invoice number, PO number and the specific figures, and say exactly what we need back (for example a credit note or a corrected tax invoice). Sign off as "Accounts Payable, Corio Packaging".
- Internal notes: short and direct, addressed to the named person or team, saying what decision or action is needed from them.
- Never include, request or agree to change bank account details.

Australian English. Plain text in drafts, no markdown."""


def facts_for(match: MatchResult, inv: InvoiceDocument, master: MasterData, requests: list[DraftRequest]) -> dict:
    vendor = master.vendor(match.vendor_id) if match.vendor_id else None
    po = master.po(match.po_number)
    return {
        "invoice": {
            "vendor_as_printed": inv.vendor_name,
            "vendor_on_file": vendor.name if vendor else None,
            "invoice_number": inv.invoice_number,
            "invoice_date": inv.invoice_date.isoformat(),
            "po_number": inv.po_number,
            "buyer": po.buyer if po else None,
            "total_inc_gst": aud(inv.total),
            "remarks_on_invoice": inv.remarks,
        },
        "findings": [
            {"type": e.type.label, "owner": e.owner, "line": e.line, "finding": e.message, "details": e.details}
            for e in match.exceptions
        ],
        "draft_requests": [asdict(r) for r in requests],
    }


def run_exception_agent(match: MatchResult, inv: InvoiceDocument, master: MasterData) -> tuple[LLMResult[ExceptionAnalysis], list[DraftRequest]]:
    requests = plan_drafts(match, inv, master)
    facts = facts_for(match, inv, master, requests)
    result = structured_call(
        system=SYSTEM,
        content=[{"type": "text", "text": "Findings for this invoice:\n\n" + json.dumps(facts, indent=2)}],
        output_format=ExceptionAnalysis,
        effort="medium",
    )
    # Recipients are code's decision, not the model's.
    drafts = result.output.drafts
    for req, draft in zip(requests, drafts):
        draft.kind, draft.to = req.kind, req.to
    result.output.drafts = drafts[: len(requests)]
    return result, requests
