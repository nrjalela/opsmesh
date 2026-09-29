"""Domain records: vendor master, POs, goods receipts, the AP ledger, and the
invoice as the matching engine sees it (whether typed from ground truth or
extracted from a PDF by the intake agent)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

PaymentTerms = Literal["NET14", "NET30", "EOM30"]
TaxCode = Literal["GST", "FRE"]  # GST = taxable 10%, FRE = GST-free
LineType = Literal["goods", "service"]  # services are 2-way matched (no receipt)


class Vendor(BaseModel):
    vendor_id: str
    name: str
    abn: str
    gst_registered: bool = True
    payment_terms: PaymentTerms
    category: str
    email: str
    address: list[str]
    active: bool = True


class POLine(BaseModel):
    line_no: int
    item_code: str
    description: str
    quantity: Decimal
    uom: str
    unit_price: Decimal  # ex GST
    tax_code: TaxCode = "GST"
    line_type: LineType = "goods"


class PurchaseOrder(BaseModel):
    po_number: str
    vendor_id: str
    order_date: date
    buyer: str
    lines: list[POLine]

    def line(self, line_no: int) -> POLine | None:
        return next((ln for ln in self.lines if ln.line_no == line_no), None)


class GRLine(BaseModel):
    po_line: int
    quantity: Decimal
    note: str | None = None


class GoodsReceipt(BaseModel):
    gr_number: str
    po_number: str
    receipt_date: date
    lines: list[GRLine]


class LedgerLine(BaseModel):
    po_line: int
    quantity: Decimal


class PostedInvoice(BaseModel):
    """An invoice already posted in the ERP (the AP sub-ledger history)."""

    document_number: str
    vendor_id: str
    invoice_number: str
    invoice_date: date
    posted_date: date
    po_number: str | None
    total: Decimal
    lines: list[LedgerLine] = Field(default_factory=list)


class InvoiceLine(BaseModel):
    description: str
    item_code: str | None = None
    po_line: int | None = None
    quantity: Decimal
    uom: str | None = None
    unit_price: Decimal  # ex GST
    amount: Decimal  # ex GST line total
    gst_applicable: bool | None = None  # None = invoice doesn't say per line


class InvoiceDocument(BaseModel):
    vendor_name: str
    vendor_abn: str
    invoice_number: str
    invoice_date: date
    po_number: str | None = None
    currency: str = "AUD"
    lines: list[InvoiceLine]
    subtotal: Decimal  # ex GST
    gst_amount: Decimal
    total: Decimal  # inc GST
    remarks: str | None = None
