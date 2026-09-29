"""Three-way match: purchase order vs goods receipt vs invoice.

Deliberately plain, deterministic code. Every decision is a rule you can read,
test, and explain to an auditor; the same input always gives the same answer.
The LLM agents sit either side of this (reading the PDF, explaining the
result) but never decide whether an invoice matches.

Order of checks mirrors how an AP officer works an invoice:
  1. Arithmetic      - does the document add up?
  2. Vendor          - is this ABN in the vendor master?        (stop if not)
  3. Duplicate       - have we already posted this invoice?     (stop if so)
  4. Purchase order  - does the PO exist and belong to the vendor?
  5. Lines           - price vs PO; qty vs receipt (goods) or PO (services)
  6. GST             - 10% of the taxable lines, using the PO tax codes
"""

from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal
from difflib import SequenceMatcher
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from opsmesh.config import Tolerances
from opsmesh.engine.abn import format_abn, is_valid_abn
from opsmesh.engine.master import MasterData
from opsmesh.engine.models import InvoiceDocument, InvoiceLine, POLine, PurchaseOrder, Vendor
from opsmesh.engine.money import aud, cents, pct, price, qty


class ExceptionType(str, Enum):
    # The six seeded in the demo dataset
    PRICE_VARIANCE = "price_variance"
    SHORT_SHIPPED = "short_shipped"
    DUPLICATE_INVOICE = "duplicate_invoice"
    MISSING_GOODS_RECEIPT = "missing_goods_receipt"
    UNKNOWN_VENDOR = "unknown_vendor"
    GST_ERROR = "gst_error"
    # Also handled by the engine
    PO_NOT_FOUND = "po_not_found"
    LINE_NOT_ON_PO = "line_not_on_po"
    OVER_PO_QUANTITY = "over_po_quantity"
    INVOICE_MATH = "invoice_math"

    @property
    def label(self) -> str:
        return EXCEPTION_LABELS[self]

    @property
    def owner(self) -> str:
        return EXCEPTION_OWNERS[self]


EXCEPTION_LABELS = {
    ExceptionType.PRICE_VARIANCE: "Price higher than PO",
    ExceptionType.SHORT_SHIPPED: "Billed for more than we received",
    ExceptionType.DUPLICATE_INVOICE: "Duplicate invoice",
    ExceptionType.MISSING_GOODS_RECEIPT: "No goods receipt yet",
    ExceptionType.UNKNOWN_VENDOR: "Vendor not in master",
    ExceptionType.GST_ERROR: "GST doesn't add up",
    ExceptionType.PO_NOT_FOUND: "PO missing or not found",
    ExceptionType.LINE_NOT_ON_PO: "Line not on the PO",
    ExceptionType.OVER_PO_QUANTITY: "Billed more than ordered",
    ExceptionType.INVOICE_MATH: "Invoice doesn't add up",
}

# Who has to act to clear it (drives the drafted email / note).
EXCEPTION_OWNERS = {
    ExceptionType.PRICE_VARIANCE: "Procurement (buyer)",
    ExceptionType.SHORT_SHIPPED: "Vendor",
    ExceptionType.DUPLICATE_INVOICE: "Accounts payable",
    ExceptionType.MISSING_GOODS_RECEIPT: "Receiving (warehouse)",
    ExceptionType.UNKNOWN_VENDOR: "Vendor master team",
    ExceptionType.GST_ERROR: "Vendor",
    ExceptionType.PO_NOT_FOUND: "Procurement (buyer)",
    ExceptionType.LINE_NOT_ON_PO: "Procurement (buyer)",
    ExceptionType.OVER_PO_QUANTITY: "Procurement (buyer)",
    ExceptionType.INVOICE_MATH: "Vendor",
}

Outcome = Literal["pass", "fail", "info"]


class MatchException(BaseModel):
    type: ExceptionType
    message: str
    line: int | None = None  # 1-based invoice line
    details: dict[str, str] = Field(default_factory=dict)

    @property
    def owner(self) -> str:
        return self.type.owner


class TraceStep(BaseModel):
    check: str
    outcome: Outcome
    detail: str


class LineResult(BaseModel):
    invoice_line: int
    description: str
    po_line: int | None = None
    match_method: str | None = None
    line_type: str | None = None
    tax_code: str | None = None
    po_price: Decimal | None = None
    invoice_price: Decimal
    price_variance_pct: Decimal | None = None
    ordered_qty: Decimal | None = None
    received_qty: Decimal | None = None
    previously_invoiced_qty: Decimal | None = None
    invoiced_qty: Decimal
    amount: Decimal


class MatchResult(BaseModel):
    invoice_number: str
    vendor_id: str | None = None
    vendor_name: str | None = None
    po_number: str | None = None
    exceptions: list[MatchException] = Field(default_factory=list)
    lines: list[LineResult] = Field(default_factory=list)
    trace: list[TraceStep] = Field(default_factory=list)
    taxable_amount: Decimal | None = None
    expected_gst: Decimal | None = None
    invoice_total: Decimal

    @property
    def is_clean(self) -> bool:
        return not self.exceptions

    @property
    def exception_types(self) -> list[ExceptionType]:
        seen: list[ExceptionType] = []
        for e in self.exceptions:
            if e.type not in seen:
                seen.append(e.type)
        return seen

    @property
    def summary(self) -> str:
        if self.is_clean:
            return "Matched: PO, receipt and invoice agree"
        labels = ", ".join(t.label.lower() for t in self.exception_types)
        n = len(self.exceptions)
        return f"{n} exception{'s' if n > 1 else ''}: {labels}"

    # helpers used while building the result
    def _pass(self, check: str, detail: str) -> None:
        self.trace.append(TraceStep(check=check, outcome="pass", detail=detail))

    def _info(self, check: str, detail: str) -> None:
        self.trace.append(TraceStep(check=check, outcome="info", detail=detail))

    def _fail(self, check: str, exc: MatchException) -> None:
        self.exceptions.append(exc)
        self.trace.append(TraceStep(check=check, outcome="fail", detail=exc.message))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def match_invoice(inv: InvoiceDocument, master: MasterData, tol: Tolerances) -> MatchResult:
    r = MatchResult(invoice_number=inv.invoice_number, po_number=inv.po_number, invoice_total=inv.total)

    _check_arithmetic(inv, tol, r)

    vendor = _check_vendor(inv, master, r)
    if vendor is None:
        return r
    r.vendor_id, r.vendor_name = vendor.vendor_id, vendor.name

    if _check_duplicate(inv, vendor, master, tol, r):
        return r

    po = _check_po(inv, vendor, master, r)
    if po is not None:
        r.po_number = po.po_number
        _match_lines(inv, po, master, tol, r)
    else:
        r.lines = [_unmatched_line(i, ln) for i, ln in enumerate(inv.lines, 1)]

    _check_gst(inv, vendor, tol, r)
    return r


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _close(a: Decimal, b: Decimal, tolerance: Decimal) -> bool:
    return abs(Decimal(a) - Decimal(b)) <= tolerance


def _check_arithmetic(inv: InvoiceDocument, tol: Tolerances, r: MatchResult) -> None:
    t = tol.arithmetic.tolerance
    problems: list[str] = []
    for i, ln in enumerate(inv.lines, 1):
        if not _close(ln.quantity * ln.unit_price, ln.amount, t):
            problems.append(
                f"line {i}: {qty(ln.quantity)} x {price(ln.unit_price)} = "
                f"{aud(ln.quantity * ln.unit_price)}, but the line shows {aud(ln.amount)}"
            )
    line_sum = sum((ln.amount for ln in inv.lines), Decimal("0"))
    if not _close(line_sum, inv.subtotal, t):
        problems.append(f"lines add to {aud(line_sum)} but the subtotal shows {aud(inv.subtotal)}")
    if not _close(inv.subtotal + inv.gst_amount, inv.total, t):
        problems.append(
            f"subtotal {aud(inv.subtotal)} + GST {aud(inv.gst_amount)} = "
            f"{aud(inv.subtotal + inv.gst_amount)}, but the total shows {aud(inv.total)}"
        )
    if problems:
        r._fail(
            "Arithmetic",
            MatchException(
                type=ExceptionType.INVOICE_MATH,
                message="The invoice doesn't add up: " + "; ".join(problems) + ".",
            ),
        )
    else:
        r._pass("Arithmetic", f"Lines, subtotal, GST and total add up ({aud(inv.total)} inc GST).")


def _check_vendor(inv: InvoiceDocument, master: MasterData, r: MatchResult) -> Vendor | None:
    vendor = master.vendor_by_abn(inv.vendor_abn)
    if vendor is not None and vendor.active:
        r._pass("Vendor", f"ABN {format_abn(inv.vendor_abn)} is {vendor.name} ({vendor.vendor_id}).")
        return vendor

    details: dict[str, str] = {"abn": format_abn(inv.vendor_abn)}
    if not is_valid_abn(inv.vendor_abn):
        details["abn_checksum"] = "fails"
    lookalike = master.vendor_by_name(inv.vendor_name)
    red_flag = bool(inv.remarks and re.search(r"bank|account details", inv.remarks, re.I))
    if red_flag:
        details["bank_details_change"] = "mentioned on invoice"

    if vendor is not None:  # known ABN, but the record is blocked
        msg = f"{vendor.name} ({vendor.vendor_id}) is blocked/inactive in the vendor master."
    elif lookalike is not None:
        details["lookalike_vendor"] = lookalike.vendor_id
        msg = (
            f"ABN {format_abn(inv.vendor_abn)} isn't in the vendor master, but the name matches "
            f"{lookalike.name} ({lookalike.vendor_id}), whose ABN on file is {format_abn(lookalike.abn)}. "
            "This could be a restructure or an impersonation attempt. Verify with the vendor using "
            "the contact details already on file, not the ones printed on this invoice."
        )
    else:
        msg = (
            f"{inv.vendor_name} (ABN {format_abn(inv.vendor_abn)}) isn't set up in the vendor master. "
            "A new vendor needs onboarding (ABN lookup, verified bank details) before anything can be paid."
        )
    if "abn_checksum" in details:
        msg += " The ABN also fails the ATO checksum."
    if red_flag:
        msg += " The invoice asks us to pay into changed bank details, which is a common fraud pattern."
    r._fail("Vendor", MatchException(type=ExceptionType.UNKNOWN_VENDOR, message=msg, details=details))
    return None


def normalise_invoice_number(number: str) -> str:
    """'INV-004417', 'inv 4417' and '4417' all become '4417'."""
    digits = re.sub(r"\D", "", number)
    if digits:
        return digits.lstrip("0") or "0"
    return re.sub(r"[^A-Z0-9]", "", number.upper())


def _check_duplicate(
    inv: InvoiceDocument, vendor: Vendor, master: MasterData, tol: Tolerances, r: MatchResult
) -> bool:
    key = normalise_invoice_number(inv.invoice_number)
    for posted in master.ledger_for_vendor(vendor.vendor_id):
        when = posted.posted_date.strftime("%-d %b %Y")
        ref = f"document {posted.document_number}, {aud(posted.total)}"
        if posted.invoice_number.strip().upper() == inv.invoice_number.strip().upper():
            kind = "exact"
            msg = (
                f"Invoice {inv.invoice_number} from {vendor.name} was already posted on {when} "
                f"({ref}). This is a resent copy. Paying it would pay the vendor twice."
            )
        elif normalise_invoice_number(posted.invoice_number) == key:
            kind = "number_format"
            msg = (
                f"Invoice {inv.invoice_number} matches posted invoice '{posted.invoice_number}' once "
                f"prefixes and leading zeros are ignored (posted {when}, {ref})."
            )
        elif (
            _close(posted.total, inv.total, Decimal("0.01"))
            and abs((posted.invoice_date - inv.invoice_date).days) <= tol.duplicates.window_days
        ):
            kind = "amount_and_date"
            msg = (
                f"Same vendor and same total ({aud(inv.total)}) as invoice {posted.invoice_number}, "
                f"dated within {tol.duplicates.window_days} days of it (posted {when}, "
                f"document {posted.document_number}). Possibly the same charge under a new number."
            )
        else:
            continue
        r._fail(
            "Duplicate",
            MatchException(
                type=ExceptionType.DUPLICATE_INVOICE,
                message=msg,
                details={"match": kind, "posted_document": posted.document_number,
                         "posted_invoice_number": posted.invoice_number},
            ),
        )
        return True
    r._pass("Duplicate", f"No earlier invoice from {vendor.name} matches this number, amount or date.")
    return False


def _check_po(inv: InvoiceDocument, vendor: Vendor, master: MasterData, r: MatchResult) -> PurchaseOrder | None:
    if not inv.po_number:
        r._fail(
            "Purchase order",
            MatchException(
                type=ExceptionType.PO_NOT_FOUND,
                message="The invoice has no PO number. It needs a PO raised (or a non-PO approval) before it can be matched.",
            ),
        )
        return None
    po = master.po(inv.po_number)
    if po is None:
        r._fail(
            "Purchase order",
            MatchException(
                type=ExceptionType.PO_NOT_FOUND,
                message=f"PO {inv.po_number} doesn't exist in the system.",
            ),
        )
        return None
    if po.vendor_id != vendor.vendor_id:
        other = master.vendor(po.vendor_id)
        r._fail(
            "Purchase order",
            MatchException(
                type=ExceptionType.PO_NOT_FOUND,
                message=f"PO {po.po_number} was raised with {other.name if other else po.vendor_id}, not {vendor.name}.",
            ),
        )
        return None
    r._pass("Purchase order", f"PO {po.po_number} ({len(po.lines)} line{'s' if len(po.lines) > 1 else ''}, buyer {po.buyer}).")
    return po


def _find_po_line(ln: InvoiceLine, po: PurchaseOrder) -> tuple[POLine | None, str | None]:
    if ln.po_line is not None and (pol := po.line(ln.po_line)) is not None:
        return pol, "PO line reference"
    if ln.item_code:
        code = ln.item_code.strip().upper()
        for pol in po.lines:
            if pol.item_code.upper() == code:
                return pol, "item code"
    best, score = None, 0.0
    for pol in po.lines:
        s = SequenceMatcher(None, ln.description.lower(), pol.description.lower()).ratio()
        if s > score:
            best, score = pol, s
    if best is not None and score >= 0.6:
        return best, f"description ({score:.0%} similar)"
    return None, None


def _unmatched_line(i: int, ln: InvoiceLine) -> LineResult:
    return LineResult(
        invoice_line=i, description=ln.description, invoice_price=ln.unit_price,
        invoiced_qty=ln.quantity, amount=ln.amount,
    )


def _match_lines(
    inv: InvoiceDocument, po: PurchaseOrder, master: MasterData, tol: Tolerances, r: MatchResult
) -> None:
    consumed: dict[int, Decimal] = defaultdict(Decimal)  # qty billed earlier on this same invoice
    for i, ln in enumerate(inv.lines, 1):
        pol, method = _find_po_line(ln, po)
        if pol is None:
            r.lines.append(_unmatched_line(i, ln))
            r._fail(
                f"Line {i}",
                MatchException(
                    type=ExceptionType.LINE_NOT_ON_PO, line=i,
                    message=f"Line {i} ({ln.description}, {aud(ln.amount)}) doesn't match any line on PO {po.po_number}.",
                ),
            )
            continue

        prev = master.invoiced_qty(po.po_number, pol.line_no) + consumed[pol.line_no]
        received = master.received_qty(po.po_number, pol.line_no) if pol.line_type == "goods" else None
        variance = ln.unit_price - pol.unit_price
        var_pct = variance / pol.unit_price if pol.unit_price else Decimal("0")
        lr = LineResult(
            invoice_line=i, description=pol.description, po_line=pol.line_no, match_method=method,
            line_type=pol.line_type, tax_code=pol.tax_code, po_price=pol.unit_price,
            invoice_price=ln.unit_price, price_variance_pct=var_pct.quantize(Decimal("0.0001")),
            ordered_qty=pol.quantity, received_qty=received, previously_invoiced_qty=prev,
            invoiced_qty=ln.quantity, amount=ln.amount,
        )
        r.lines.append(lr)
        label = f"Line {i}"
        r._info(label, f"Matched to PO line {pol.line_no} ({pol.description}) by {method}.")

        _check_price(i, ln, pol, variance, var_pct, tol, r)
        if pol.line_type == "service":
            _check_service_qty(i, ln, pol, prev, r)
        else:
            _check_goods_qty(i, ln, pol, po, prev, received or Decimal("0"), master, tol, r)
        consumed[pol.line_no] += ln.quantity


def _check_price(
    i: int, ln: InvoiceLine, pol: POLine, variance: Decimal, var_pct: Decimal, tol: Tolerances, r: MatchResult
) -> None:
    label = f"Line {i} price"
    over_value = cents(variance * ln.quantity)
    limits = f"limit {tol.price.pct * 100:.0f}% or {aud(tol.price.abs_per_line)} per line, whichever is lower"
    if variance > 0 and (var_pct > tol.price.pct or over_value > tol.price.abs_per_line):
        breached = "percentage" if var_pct > tol.price.pct else "dollar"
        if var_pct > tol.price.pct and over_value > tol.price.abs_per_line:
            breached = "percentage and dollar"
        r._fail(
            label,
            MatchException(
                type=ExceptionType.PRICE_VARIANCE, line=i,
                message=(
                    f"Line {i} ({pol.description}): billed {price(ln.unit_price)}/{pol.uom} against a PO price of "
                    f"{price(pol.unit_price)} ({pct(var_pct)}, {aud(over_value)} over on this line). "
                    f"Breaches the {breached} limit ({limits})."
                ),
                details={"po_price": str(pol.unit_price), "invoice_price": str(ln.unit_price),
                         "variance_pct": f"{var_pct:.4f}", "over_value": str(over_value), "breached": breached},
            ),
        )
    elif variance > 0:
        r._pass(label, f"{price(ln.unit_price)} vs PO {price(pol.unit_price)} ({pct(var_pct)}, {aud(over_value)}): within tolerance ({limits}).")
    elif variance < 0:
        r._info(label, f"{price(ln.unit_price)} is below the PO price of {price(pol.unit_price)} ({pct(var_pct)}). No block for undercharging.")
    else:
        r._pass(label, f"{price(ln.unit_price)}/{pol.uom} agrees with the PO.")


def _check_goods_qty(
    i: int, ln: InvoiceLine, pol: POLine, po: PurchaseOrder, prev: Decimal, received: Decimal,
    master: MasterData, tol: Tolerances, r: MatchResult,
) -> None:
    label = f"Line {i} quantity"
    available = received - prev
    u = pol.uom
    if available <= 0:
        if received == 0:
            msg = (
                f"Line {i} ({pol.description}): no goods receipt has been recorded against PO {po.po_number} "
                f"line {pol.line_no}. Receiving needs to confirm the {qty(ln.quantity)} {u} arrived before this can be paid."
            )
        else:
            msg = (
                f"Line {i} ({pol.description}): everything received so far on PO {po.po_number} line {pol.line_no} "
                f"({qty(received)} {u}) has already been invoiced. This invoice bills another {qty(ln.quantity)} {u} "
                "that hasn't been receipted yet."
            )
        r._fail(
            label,
            MatchException(
                type=ExceptionType.MISSING_GOODS_RECEIPT, line=i, message=msg,
                details={"received": str(received), "previously_invoiced": str(prev), "invoiced": str(ln.quantity)},
            ),
        )
        return
    allowed = available * (1 + tol.quantity.over_receipt_pct)
    if ln.quantity > allowed:
        short = ln.quantity - available
        notes = [n for _, _, n in master.receipts_for(po.po_number, pol.line_no) if n]
        msg = (
            f"Line {i} ({pol.description}): billed {qty(ln.quantity)} {u}, but only {qty(available)} {u} "
            f"have been received and not yet invoiced ({qty(short)} {u} short, {aud(short * ln.unit_price)} ex GST)."
        )
        if notes:
            msg += " Receiving note: " + "; ".join(notes) + "."
        r._fail(
            label,
            MatchException(
                type=ExceptionType.SHORT_SHIPPED, line=i, message=msg,
                details={"received": str(received), "previously_invoiced": str(prev),
                         "invoiced": str(ln.quantity), "short": str(short)},
            ),
        )
        return
    prev_txt = f", {qty(prev)} already invoiced" if prev else ""
    r._pass(label, f"Billed {qty(ln.quantity)} {u}; received {qty(received)} {u}{prev_txt}. Covered by receipts.")


def _check_service_qty(i: int, ln: InvoiceLine, pol: POLine, prev: Decimal, r: MatchResult) -> None:
    label = f"Line {i} quantity"
    remaining = pol.quantity - prev
    if ln.quantity > remaining:
        r._fail(
            label,
            MatchException(
                type=ExceptionType.OVER_PO_QUANTITY, line=i,
                message=(
                    f"Line {i} ({pol.description}): billed {qty(ln.quantity)} {pol.uom} but only {qty(remaining)} "
                    f"{pol.uom} remain on the PO ({qty(pol.quantity)} ordered, {qty(prev)} already invoiced)."
                ),
            ),
        )
    else:
        r._pass(
            label,
            f"Service line, two-way match: billed {qty(ln.quantity)} {pol.uom} of {qty(remaining)} remaining on the PO. No goods receipt needed.",
        )


def _check_gst(inv: InvoiceDocument, vendor: Vendor, tol: Tolerances, r: MatchResult) -> None:
    by_line = {lr.invoice_line: lr for lr in r.lines}
    taxable, free_lines = Decimal("0"), []
    for i, ln in enumerate(inv.lines, 1):
        lr = by_line.get(i)
        if lr is not None and lr.tax_code is not None:
            is_taxable = lr.tax_code == "GST"  # the PO tax code is the source of truth
        else:
            is_taxable = ln.gst_applicable is not False
        if is_taxable:
            taxable += ln.amount
        else:
            free_lines.append((i, ln))

    rate = tol.gst.rate if vendor.gst_registered else Decimal("0")
    expected = cents(taxable * rate)
    r.taxable_amount, r.expected_gst = cents(taxable), expected
    diff = cents(inv.gst_amount - expected)

    if abs(diff) <= tol.gst.rounding:
        extra = f" {len(free_lines)} GST-free line(s) correctly excluded." if free_lines else ""
        r._pass("GST", f"GST {aud(inv.gst_amount)} = 10% of {aud(taxable)} taxable.{extra}")
        return

    if not vendor.gst_registered and inv.gst_amount > 0:
        msg = f"{vendor.name} isn't registered for GST but has charged {aud(inv.gst_amount)} GST."
        cause = "vendor_not_registered"
    else:
        all_lines = sum((ln.amount for ln in inv.lines), Decimal("0"))
        charged_on_free = free_lines and _close(inv.gst_amount, cents(all_lines * tol.gst.rate), tol.gst.rounding)
        if charged_on_free:
            names = ", ".join(f"line {i} ({ln.description})" for i, ln in free_lines)
            msg = (
                f"GST has been charged on GST-free {names}. Expected GST is {aud(expected)} "
                f"(10% of {aud(taxable)} taxable) but the invoice shows {aud(inv.gst_amount)}, "
                f"{aud(abs(diff))} too much. Ask the vendor for a corrected tax invoice."
            )
            cause = "gst_on_gst_free"
        else:
            msg = (
                f"GST shown is {aud(inv.gst_amount)}, but 10% of the taxable {aud(taxable)} is {aud(expected)}: "
                f"out by {aud(abs(diff))}, more than the {aud(tol.gst.rounding)} rounding allowance. "
                "Ask the vendor for a corrected tax invoice."
            )
            cause = "miscalculated"
    r._fail(
        "GST",
        MatchException(
            type=ExceptionType.GST_ERROR, message=msg,
            details={"expected_gst": str(expected), "invoice_gst": str(inv.gst_amount),
                     "difference": str(diff), "cause": cause},
        ),
    )
