"""Tiny, explicit fixtures so each test reads like the AP scenario it covers."""

from __future__ import annotations

from datetime import date
from decimal import Decimal as D

from opsmesh.engine.master import MasterData
from opsmesh.engine.models import (
    GoodsReceipt, GRLine, InvoiceDocument, InvoiceLine, LedgerLine, POLine, PostedInvoice, PurchaseOrder, Vendor,
)
from opsmesh.engine.money import cents

ABN = "51824753556"  # the ATO's published example ABN (checksum-valid)
OTHER_ABN = "83914571673"
PO = "4500000001"

VENDOR = Vendor(
    vendor_id="V1", name="Test Resins Pty Ltd", abn=ABN, payment_terms="NET30", category="Resin",
    email="ar@testresins.example", address=["1 Test St", "Corio VIC 3214"],
)
OTHER_VENDOR = Vendor(
    vendor_id="V2", name="Other Supplies Pty Ltd", abn=OTHER_ABN, payment_terms="NET30", category="MRO",
    email="ar@other.example", address=["2 Test St", "Corio VIC 3214"],
)

PO_LINES = [
    POLine(line_no=10, item_code="RES-A", description="Resin grade A", quantity=D(10), uom="t", unit_price=D("1000.00")),
    POLine(line_no=20, item_code="FRT-INT", description="International sea freight", quantity=D(1), uom="ctr",
           unit_price=D("2000.00"), tax_code="FRE", line_type="service"),
    POLine(line_no=30, item_code="SVC-HR", description="Technician labour", quantity=D(10), uom="hr",
           unit_price=D("100.00"), line_type="service"),
    POLine(line_no=40, item_code="CHM-BULK", description="Bulk caustic soda", quantity=D(2000), uom="L",
           unit_price=D("10.00")),
    POLine(line_no=50, item_code="RES-B", description="Resin grade B", quantity=D(5), uom="t", unit_price=D("1500.00")),
]
PO_BY_CODE = {ln.item_code: ln for ln in PO_LINES}


def master(receipts: dict[int, list[int]] | None = None, ledger: list[PostedInvoice] | None = None,
           vendors: list[Vendor] | None = None, extra_pos: list[PurchaseOrder] | None = None) -> MasterData:
    """Default: lines 10 and 40 fully received; line 50 (RES-B) never received."""
    receipts = {10: [10], 40: [2000]} if receipts is None else receipts
    grs = []
    for line_no, deliveries in receipts.items():
        for k, q in enumerate(deliveries):
            grs.append(GoodsReceipt(gr_number=f"50000{line_no}{k}", po_number=PO, receipt_date=date(2026, 9, 1),
                                    lines=[GRLine(po_line=line_no, quantity=D(q))]))
    pos = [PurchaseOrder(po_number=PO, vendor_id="V1", order_date=date(2026, 8, 1), buyer="T. Buyer", lines=PO_LINES)]
    return MasterData(
        vendors=vendors if vendors is not None else [VENDOR, OTHER_VENDOR],
        purchase_orders=pos + (extra_pos or []),
        goods_receipts=grs,
        ledger=ledger or [],
    )


def posted(number: str, total: str, *, vendor_id: str = "V1", inv_date: date = date(2026, 8, 10),
           lines: list[tuple[int, int]] | None = None) -> PostedInvoice:
    return PostedInvoice(
        document_number="5105000001", vendor_id=vendor_id, invoice_number=number, invoice_date=inv_date,
        posted_date=inv_date, po_number=PO, total=D(total),
        lines=[LedgerLine(po_line=l, quantity=D(q)) for l, q in (lines or [])],
    )


def invoice(lines: list[tuple[str, float | int, str | None]], *, number: str = "INV-100", abn: str = ABN,
            name: str = "Test Resins Pty Ltd", po: str | None = PO, gst: str | None = None,
            inv_date: date = date(2026, 9, 10), gst_on_free: bool = False, remarks: str | None = None,
            total: str | None = None) -> InvoiceDocument:
    """lines: (item_code, qty, unit_price or None for PO price). GST computed correctly unless overridden."""
    inv_lines = []
    for code, q, p in lines:
        pol = PO_BY_CODE.get(code)
        unit = D(p) if p is not None else pol.unit_price
        taxable = gst_on_free or pol is None or pol.tax_code == "GST"
        inv_lines.append(InvoiceLine(
            description=pol.description if pol else code, item_code=code, quantity=D(str(q)),
            uom=pol.uom if pol else "ea", unit_price=unit, amount=cents(D(str(q)) * unit), gst_applicable=taxable,
        ))
    subtotal = sum((ln.amount for ln in inv_lines), D("0"))
    gst_amt = D(gst) if gst is not None else cents(sum((ln.amount for ln in inv_lines if ln.gst_applicable), D("0")) * D("0.1"))
    return InvoiceDocument(
        vendor_name=name, vendor_abn=abn, invoice_number=number, invoice_date=inv_date, po_number=po,
        lines=inv_lines, subtotal=subtotal, gst_amount=gst_amt,
        total=D(total) if total is not None else subtotal + gst_amt, remarks=remarks,
    )
