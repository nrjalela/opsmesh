"""Intake agent: read the invoice PDF into a validated, confidence-scored schema."""

from __future__ import annotations

import base64
from pathlib import Path

from opsmesh.agents.llm import LLMResult, structured_call
from opsmesh.agents.schema import InvoiceExtraction
from opsmesh.config import load_company

SYSTEM = """You are the intake step in the accounts payable pipeline of {company} (ABN {abn}), a packaging manufacturer in Geelong, Australia. You read one supplier invoice and transcribe it into the schema.

A deterministic matching engine checks your output against purchase orders, goods receipts and the AP ledger. So transcribe exactly what is printed, including the vendor's own arithmetic, prices and GST, even where they look wrong. Correcting a vendor's mistake would hide it from the checks that exist to catch it.

Guidance:
- The vendor is the supplier issuing the invoice. {company} is the customer (Bill To / Sold To / To), never the vendor.
- Dates are day-first on Australian documents: 09/10/2026 is 9 October 2026. Return ISO YYYY-MM-DD.
- The PO number may be labelled Your Order No., PO number, Reference or similar.
- One entry per printed line item. unit_price and amount are excluding GST; if the invoice shows ex-GST, GST and inc-GST columns, use the ex-GST figures. Quantity is the number only; the unit goes in uom.
- item_code and po_line only when the document prints them for that line.
- Totals come from the totals block as printed.
- Confidence: use 0.95 or higher only for values that are clearly printed and unambiguous. Lower it when a value is hard to read, ambiguous, or had to be inferred. A field that is genuinely absent from the document gets null with high confidence."""


def _content(pdf_path: Path, received_date: str | None) -> list[dict]:
    data = base64.standard_b64encode(Path(pdf_path).read_bytes()).decode("ascii")
    note = f" It was received by accounts payable on {received_date}." if received_date else ""
    return [
        {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": data}},
        {"type": "text", "text": f"Transcribe this supplier invoice.{note}"},
    ]


def run_intake(pdf_path: Path, received_date: str | None = None) -> LLMResult[InvoiceExtraction]:
    company = load_company()
    return structured_call(
        system=SYSTEM.format(company=company.name, abn=company.abn),
        content=_content(pdf_path, received_date),
        output_format=InvoiceExtraction,
        effort="medium",
    )
