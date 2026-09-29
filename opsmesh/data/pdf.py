"""Render synthetic tax invoices as PDFs.

Four layouts stand in for four kinds of vendor billing system, so the intake
agent has to read the document rather than parse a fixed format:

  classic   - small-business accounting package (Times, boxed header)
  modern    - SaaS invoicing tool (colour band, per-line GST, inc-GST column)
  compact   - old ERP print run (Courier, PO line column, DD-MON-YY dates)
  services  - contractor letter style (hours x rate, no item codes)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from opsmesh.config import Company
from opsmesh.engine.abn import format_abn
from opsmesh.engine.terms import TERMS_TEXT

W, H = A4
M = 42  # page margin
GREY = HexColor("#666666")
LIGHT = HexColor("#eeeeee")
DISCLAIMER = (
    "SYNTHETIC DOCUMENT generated for the OpsMesh portfolio demo. Not a real tax invoice. "
    "Names, ABNs and addresses are fictional."
)


@dataclass
class PrintedLine:
    code: str
    po_line: int | None
    description: str
    qty: Decimal
    uom: str
    unit_price: Decimal
    amount: Decimal
    gst_applicable: bool
    gst: Decimal


@dataclass
class PrintedInvoice:
    doc_id: str
    template: str
    colour: str
    vendor_name: str
    vendor_abn: str
    vendor_address: tuple[str, ...]
    vendor_email: str
    invoice_number: str
    invoice_date: date
    due_date: date
    terms: str
    po_number: str | None
    lines: list[PrintedLine]
    subtotal: Decimal
    gst: Decimal
    total: Decimal
    remarks: str | None
    buyer: Company
    docket: str


# --- formatting helpers ------------------------------------------------------

def money(v: Decimal) -> str:
    return f"{v:,.2f}"


def unit_price(v: Decimal) -> str:
    v = Decimal(v)
    return f"{v:,.3f}" if v != v.quantize(Decimal("0.01")) else f"{v:,.2f}"


def quantity(v: Decimal) -> str:
    v = Decimal(v)
    return f"{int(v):,}" if v == v.to_integral() else f"{v.normalize():,f}"


# --- shared drawing ------------------------------------------------------------

def _text(c: Canvas, x: float, y: float, s: str, font: str = "Helvetica", size: float = 9,
          align: str = "left", colour=None) -> None:
    c.setFont(font, size)
    if colour is not None:
        c.setFillColor(colour)
    if align == "right":
        c.drawRightString(x, y, s)
    elif align == "centre":
        c.drawCentredString(x, y, s)
    else:
        c.drawString(x, y, s)
    if colour is not None:
        c.setFillColorRGB(0, 0, 0)


def _table(c: Canvas, x: float, y: float, cols: list[tuple[str, float, str]], rows: list[list[str]],
           font: str, size: float, head_font: str, head_fill=LIGHT, head_text=None, wrap_col: int = 1,
           rule: bool = True) -> float:
    """Draw a simple table; returns the y below it. One column may wrap."""
    leading = size + 3
    total_w = sum(w for _, w, _ in cols)
    if head_fill is not None:
        c.setFillColor(head_fill)
        c.rect(x, y - leading - 3, total_w, leading + 5, stroke=0, fill=1)
        c.setFillColorRGB(0, 0, 0)
    cx = x
    for title, w, align in cols:
        tx = cx + w - 4 if align == "right" else cx + 4
        _text(c, tx, y - leading + 1, title, head_font, size, align, head_text)
        cx += w
    y -= leading + 8
    for row in rows:
        wrapped = simpleSplit(row[wrap_col], font, size, cols[wrap_col][1] - 8)
        height = leading * max(1, len(wrapped))
        cx = x
        for i, (cell, (_, w, align)) in enumerate(zip(row, cols)):
            lines = wrapped if i == wrap_col else [cell]
            for k, part in enumerate(lines):
                tx = cx + w - 4 if align == "right" else cx + 4
                _text(c, tx, y - leading * k - leading + 3, part, font, size, align)
            cx += w
        y -= height + 3
        if rule:
            c.setStrokeColor(LIGHT)
            c.line(x, y + 1, x + total_w, y + 1)
            c.setStrokeColorRGB(0, 0, 0)
    return y


def _totals(c: Canvas, x_label: float, x_val: float, y: float, rows: list[tuple[str, str]],
            font: str, bold: str, size: float = 10) -> float:
    for i, (label, value) in enumerate(rows):
        f = bold if i == len(rows) - 1 else font
        _text(c, x_label, y, label, f, size, "right")
        _text(c, x_val, y, value, f, size, "right")
        y -= size + 6
    return y


def _remarks(c: Canvas, y: float, text: str | None, font: str = "Helvetica-Bold", size: float = 9) -> float:
    if not text:
        return y
    lines = simpleSplit(text, font, size, W - 2 * M - 20)
    h = (size + 3) * len(lines) + 12
    c.setFillColor(HexColor("#fff4d6"))
    c.setStrokeColor(HexColor("#d9a400"))
    c.rect(M, y - h, W - 2 * M, h, stroke=1, fill=1)
    c.setFillColorRGB(0, 0, 0)
    for i, ln in enumerate(lines):
        _text(c, M + 10, y - 14 - i * (size + 3), ln, font, size)
    c.setStrokeColorRGB(0, 0, 0)
    return y - h - 10


def _footer(c: Canvas) -> None:
    _text(c, W / 2, 22, DISCLAIMER, "Helvetica-Oblique", 6.5, "centre", GREY)


def _buyer_lines(b: Company) -> list[str]:
    return [b.name, f"ABN {format_abn(b.abn)}", *b.address, "Attn: Accounts Payable"]


# --- templates -----------------------------------------------------------------

def _classic(c: Canvas, inv: PrintedInvoice) -> None:
    accent = HexColor(inv.colour)
    y = H - M - 6
    _text(c, M, y, inv.vendor_name, "Times-Bold", 17, colour=accent)
    for i, s in enumerate([*inv.vendor_address, f"ABN {format_abn(inv.vendor_abn)}", inv.vendor_email]):
        _text(c, M, y - 16 - i * 11, s, "Times-Roman", 9.5)
    _text(c, W - M, y, "TAX INVOICE", "Times-Bold", 19, "right")

    box_x, box_y, box_w = W - M - 210, y - 22, 210
    rows = [
        ("Invoice No.", inv.invoice_number),
        ("Date", inv.invoice_date.strftime("%d/%m/%Y")),
        ("Your Order No.", inv.po_number or "-"),
        ("Terms", TERMS_TEXT[inv.terms]),
        ("Due Date", inv.due_date.strftime("%d/%m/%Y")),
    ]
    c.rect(box_x, box_y - 14 * len(rows) - 4, box_w, 14 * len(rows) + 4)
    for i, (k, v) in enumerate(rows):
        _text(c, box_x + 6, box_y - 12 - i * 14, k, "Times-Bold", 9)
        _text(c, box_x + box_w - 6, box_y - 12 - i * 14, v, "Times-Roman", 9, "right")

    y = box_y - 14 * len(rows) - 28
    _text(c, M, y, "Bill To", "Times-Bold", 10)
    for i, s in enumerate(_buyer_lines(inv.buyer)):
        _text(c, M, y - 13 - i * 11, s, "Times-Roman", 9.5)
    _text(c, M + 260, y, "Deliver To", "Times-Bold", 10)
    for i, s in enumerate(["Corio plant, receiving dock 2", *inv.buyer.address]):
        _text(c, M + 260, y - 13 - i * 11, s, "Times-Roman", 9.5)

    y -= 13 + 11 * 5 + 16
    cols = [("Code", 88, "left"), ("Description", 190, "left"), ("Qty", 50, "right"),
            ("UOM", 38, "left"), ("Unit Price", 70, "right"), ("Amount", 75, "right")]
    rows_ = [[l.code, l.description, quantity(l.qty), l.uom, unit_price(l.unit_price),
              money(l.amount) + ("" if l.gst_applicable else " *")] for l in inv.lines]
    y = _table(c, M, y, cols, rows_, "Times-Roman", 9, "Times-Bold")

    y -= 10
    y = _totals(c, W - M - 90, W - M - 4, y, [
        ("Subtotal (ex GST)", money(inv.subtotal)), ("GST", money(inv.gst)), ("TOTAL (inc GST)", money(inv.total)),
    ], "Times-Roman", "Times-Bold")
    if any(not l.gst_applicable for l in inv.lines):
        _text(c, M, y + 30, "* GST-free supply", "Times-Italic", 8.5)
    y -= 10
    y = _remarks(c, y, inv.remarks, "Times-Bold", 9.5)
    _text(c, M, y - 4, f"Payment by EFT within terms. Please quote invoice number {inv.invoice_number} on your remittance.",
          "Times-Roman", 9)
    _text(c, M, y - 16, f"Remittances to {inv.vendor_email}", "Times-Roman", 9)


def _modern(c: Canvas, inv: PrintedInvoice) -> None:
    accent = HexColor(inv.colour)
    c.setFillColor(accent)
    c.rect(0, H - 88, W, 88, stroke=0, fill=1)
    _text(c, M, H - 50, inv.vendor_name, "Helvetica-Bold", 18, colour=white)
    _text(c, W - M, H - 50, "Tax Invoice", "Helvetica", 18, "right", white)

    y = H - 112
    for i, s in enumerate([*inv.vendor_address, f"ABN: {format_abn(inv.vendor_abn)}", inv.vendor_email]):
        _text(c, M, y - i * 11, s, "Helvetica", 8.5, colour=GREY)
    meta = [
        ("Invoice #", inv.invoice_number),
        ("Issued", inv.invoice_date.strftime("%-d %b %Y")),
        ("Due", inv.due_date.strftime("%-d %b %Y")),
        ("PO number", inv.po_number or "-"),
    ]
    for i, (k, v) in enumerate(meta):
        _text(c, W - M - 150, y - i * 13, k, "Helvetica", 9, colour=GREY)
        _text(c, W - M, y - i * 13, v, "Helvetica-Bold", 9, "right")

    y -= 66
    _text(c, M, y, "BILLED TO", "Helvetica-Bold", 8, colour=accent)
    for i, s in enumerate(_buyer_lines(inv.buyer)):
        _text(c, M, y - 13 - i * 11, s, "Helvetica", 9)

    y -= 13 + 11 * 5 + 18
    cols = [("Description", 205, "left"), ("Qty", 50, "right"), ("Unit price", 62, "right"),
            ("Ex GST", 68, "right"), ("GST", 56, "right"), ("Inc GST", 70, "right")]
    rows_ = []
    for l in inv.lines:
        rows_.append([f"{l.description} [{l.code}]", f"{quantity(l.qty)} {l.uom}", unit_price(l.unit_price),
                      money(l.amount), money(l.gst) if l.gst_applicable else "GST-free", money(l.amount + l.gst)])
    y = _table(c, M, y, cols, rows_, "Helvetica", 8.5, "Helvetica-Bold", head_fill=accent, head_text=white, wrap_col=0)

    y -= 12
    y = _totals(c, W - M - 80, W - M - 4, y, [
        ("Total ex GST", money(inv.subtotal)), ("GST", money(inv.gst)), ("Amount due (AUD)", money(inv.total)),
    ], "Helvetica", "Helvetica-Bold")
    y -= 8
    y = _remarks(c, y, inv.remarks)
    _text(c, M, y - 4, f"Terms: {TERMS_TEXT[inv.terms]}. Pay by EFT, reference {inv.invoice_number}.", "Helvetica", 8.5)
    _text(c, M, y - 16, f"Questions? {inv.vendor_email}", "Helvetica", 8.5, colour=GREY)


def _compact(c: Canvas, inv: PrintedInvoice) -> None:
    f, fb, s = "Courier", "Courier-Bold", 8.6
    y = H - M
    up = str.upper
    left = [inv.vendor_name, *inv.vendor_address, f"ABN: {format_abn(inv.vendor_abn)}", inv.vendor_email]
    right = [
        ("TAX INVOICE", ""),
        ("INVOICE NO", inv.invoice_number),
        ("DATE", up(inv.invoice_date.strftime("%d-%b-%y"))),
        ("CUST A/C", "CORIO01"),
        ("YOUR ORDER", inv.po_number or "N/A"),
        ("DOCKET", inv.docket),
        ("TERMS", up(TERMS_TEXT[inv.terms])),
    ]
    for i, t in enumerate(left):
        _text(c, M, y - i * 11, up(t) if i < len(left) - 1 else t, fb if i == 0 else f, s + (1.5 if i == 0 else 0))
    for i, (k, v) in enumerate(right):
        if not v:
            _text(c, W - M, y - i * 11, k, fb, s + 3, "right")
        else:
            _text(c, W - M - 190, y - i * 11, f"{k:<11}: {v}", f, s)

    y -= 11 * 8 + 6
    _text(c, M, y, "SOLD TO:", fb, s)
    for i, t in enumerate(_buyer_lines(inv.buyer)):
        _text(c, M + 60, y - i * 11, up(t), f, s)
    y -= 11 * 5 + 10

    c.setDash(2, 2)
    c.line(M, y, W - M, y)
    cols = [("PO LN", 40, "right"), ("ITEM", 88, "left"), ("DESCRIPTION", 175, "left"), ("QTY", 55, "right"),
            ("UOM", 36, "left"), ("PRICE", 58, "right"), ("EXTENDED", 60, "right")]
    rows_ = [[str(l.po_line or ""), l.code, up(l.description), quantity(l.qty), up(l.uom), unit_price(l.unit_price),
              money(l.amount)] for l in inv.lines]
    y = _table(c, M, y - 2, cols, rows_, f, s, fb, head_fill=None, wrap_col=2, rule=False)
    c.line(M, y, W - M, y)
    c.setDash()

    y -= 16
    y = _totals(c, W - M - 90, W - M - 4, y, [
        ("SUB-TOTAL", money(inv.subtotal)), ("GST 10%", money(inv.gst)), ("TOTAL AUD", money(inv.total)),
    ], f, fb, s + 0.6)
    y -= 6
    y = _remarks(c, y, inv.remarks, fb, s)
    _text(c, M, y - 4, "*** PLEASE REMIT BY EFT QUOTING INVOICE NUMBER ***", f, s)
    _text(c, M, y - 16, f"PAGE 1 OF 1   PRINTED {up(inv.invoice_date.strftime('%d-%b-%y'))}", f, s, colour=GREY)


def _services(c: Canvas, inv: PrintedInvoice) -> None:
    accent = HexColor(inv.colour)
    y = H - M - 4
    _text(c, M, y, inv.vendor_name, "Helvetica-Bold", 15, colour=accent)
    for i, s in enumerate([*inv.vendor_address, f"ABN {format_abn(inv.vendor_abn)}", inv.vendor_email]):
        _text(c, W - M, y - i * 11, s, "Helvetica", 8.5, "right", GREY)
    c.setStrokeColor(accent)
    c.setLineWidth(1.5)
    c.line(M, y - 64, W - M, y - 64)
    c.setLineWidth(1)
    c.setStrokeColorRGB(0, 0, 0)

    y -= 96
    _text(c, M, y, "Tax Invoice", "Helvetica-Bold", 22)
    y -= 26
    ref = f"Purchase order {inv.po_number}" if inv.po_number else "Job 142, requested by plant maintenance (no order number supplied)"
    info = [
        ("Invoice number", inv.invoice_number),
        ("Date", inv.invoice_date.strftime("%-d %B %Y")),
        ("Reference", ref),
        ("Payment due", inv.due_date.strftime("%-d %B %Y")),
    ]
    for i, (k, v) in enumerate(info):
        _text(c, M, y - i * 13, k, "Helvetica-Bold", 9.5)
        _text(c, M + 100, y - i * 13, v, "Helvetica", 9.5)
    _text(c, W - M - 170, y, "To", "Helvetica-Bold", 9.5)
    for i, s in enumerate(_buyer_lines(inv.buyer)):
        _text(c, W - M - 150, y - i * 11, s, "Helvetica", 9)

    y -= 13 * 4 + 30
    cols = [("Description of work", 290, "left"), ("Qty / hrs", 60, "right"), ("Rate", 80, "right"), ("Amount", 81, "right")]
    rows_ = [[l.description + ("" if l.gst_applicable else " (GST-free)"), quantity(l.qty), unit_price(l.unit_price),
              money(l.amount)] for l in inv.lines]
    y = _table(c, M, y, cols, rows_, "Helvetica", 9.5, "Helvetica-Bold", wrap_col=0)

    y -= 12
    y = _totals(c, W - M - 90, W - M - 4, y, [
        ("Subtotal", money(inv.subtotal)), ("GST", money(inv.gst)), ("Total due", money(inv.total)),
    ], "Helvetica", "Helvetica-Bold", 10.5)
    y -= 8
    y = _remarks(c, y, inv.remarks)
    _text(c, M, y - 4, "Thank you for your business. Payment by direct deposit; please use the invoice number as reference.",
          "Helvetica", 9)


TEMPLATES = {"classic": _classic, "modern": _modern, "compact": _compact, "services": _services}


def render_invoice(inv: PrintedInvoice, path: Path) -> None:
    c = Canvas(str(path), pagesize=A4, invariant=1)  # invariant: byte-identical output on every run
    c.setTitle(f"Tax invoice {inv.invoice_number} ({inv.doc_id}) - synthetic")
    c.setAuthor("OpsMesh synthetic data generator")
    TEMPLATES[inv.template](c, inv)
    _footer(c)
    c.showPage()
    c.save()
