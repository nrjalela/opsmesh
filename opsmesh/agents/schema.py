"""What the intake agent returns, and the deterministic checks run on it.

Every field carries the model's own confidence. That number is useful but not
calibrated, so it is never trusted alone: `validate_extraction` re-checks the
document's arithmetic and the ABN checksum in code, and the router sends
anything uncertain to a person.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, Field

from opsmesh.engine.abn import is_valid_abn, normalise_abn
from opsmesh.engine.matching import TraceStep
from opsmesh.engine.models import InvoiceDocument, InvoiceLine
from opsmesh.engine.money import aud

CONF = "0.0-1.0: how certain you are this value is exactly what is printed"


class Text(BaseModel):
    value: str | None = Field(description="As printed; null if the document doesn't show it")
    confidence: float = Field(description=CONF)


class Number(BaseModel):
    value: float | None = Field(description="Plain number, no currency symbols or thousands separators")
    confidence: float = Field(description=CONF)


class Integer(BaseModel):
    value: int | None
    confidence: float = Field(description=CONF)


class Flag(BaseModel):
    value: bool | None
    confidence: float = Field(description=CONF)


class ExtractedLine(BaseModel):
    description: Text
    item_code: Text = Field(description="Item/product code printed for this line, else null")
    po_line: Integer = Field(description="Only if the invoice prints a PO line number for this line, else null")
    quantity: Number
    uom: Text = Field(description="Unit of measure, e.g. kg, ea, roll, hr")
    unit_price: Number = Field(description="Unit price excluding GST")
    amount: Number = Field(description="Line total excluding GST")
    gst_applicable: Flag = Field(
        description="false if the line is marked GST-free; true if GST is charged on it; null if the invoice gives no per-line indication"
    )


class InvoiceExtraction(BaseModel):
    is_tax_invoice: bool = Field(description="True if the document is titled a tax invoice")
    vendor_name: Text = Field(description="The supplier issuing the invoice (not the customer)")
    vendor_abn: Text = Field(description="Supplier ABN, 11 digits, no spaces")
    invoice_number: Text
    invoice_date: Text = Field(description="ISO format YYYY-MM-DD")
    due_date: Text = Field(description="ISO format YYYY-MM-DD, null if not printed")
    po_number: Text = Field(description="The customer's purchase order number, however it is labelled; null if none")
    currency: Text
    lines: list[ExtractedLine]
    subtotal_ex_gst: Number
    gst_amount: Number
    total_inc_gst: Number
    remarks: Text = Field(
        description="Any free-text message to the customer printed on the invoice, verbatim (e.g. a notice about bank details). Not standard payment-terms boilerplate. Null if none."
    )
    notes_for_ap: str = Field(
        description="One or two sentences on anything unusual about the document that a careful AP officer would want to know. Empty string if nothing stands out."
    )


# --- field access ----------------------------------------------------------------

HEADER_FIELDS = ("vendor_name", "vendor_abn", "invoice_number", "invoice_date", "po_number",
                 "subtotal_ex_gst", "gst_amount", "total_inc_gst")
LINE_FIELDS = ("item_code", "po_line", "quantity", "unit_price", "amount")
REQUIRED = ("vendor_name", "vendor_abn", "invoice_number", "invoice_date", "total_inc_gst")


def field_confidences(x: InvoiceExtraction) -> dict[str, float]:
    out = {f: getattr(x, f).confidence for f in HEADER_FIELDS}
    for i, ln in enumerate(x.lines, 1):
        for f in ("description", *LINE_FIELDS):
            out[f"line {i} {f}"] = getattr(ln, f).confidence
    return out


def _dec(v: float | None) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except InvalidOperation:
        return None


def _date(v: str | None) -> date | None:
    try:
        return date.fromisoformat(v) if v else None
    except ValueError:
        return None


# --- validation -----------------------------------------------------------------------------

class ValidationReport(BaseModel):
    checks: list[TraceStep]
    missing: list[str]
    low_confidence: list[str]
    min_confidence: float

    @property
    def ok(self) -> bool:
        return not self.missing and not self.low_confidence


def validate_extraction(x: InvoiceExtraction, min_confidence: float, received: date | None = None) -> ValidationReport:
    checks: list[TraceStep] = []

    def add(check: str, ok: bool, good: str, bad: str, info: bool = False) -> None:
        checks.append(TraceStep(check=check, outcome="pass" if ok else ("info" if info else "fail"),
                                detail=good if ok else bad))

    missing = [f for f in REQUIRED if getattr(x, f).value in (None, "")]
    if not x.lines:
        missing.append("lines")
    add("Required fields", not missing, "Vendor, ABN, invoice number, date and total were all found.",
        "Could not read: " + ", ".join(missing) + ".")

    abn = x.vendor_abn.value
    add("ABN checksum", is_valid_abn(abn), f"ABN {normalise_abn(abn)} passes the ATO checksum.",
        f"ABN '{abn}' fails the ATO checksum (misread, or not a real ABN).")

    inv_date = _date(x.invoice_date.value)
    if x.invoice_date.value and inv_date is None:
        add("Invoice date", False, "", f"Invoice date '{x.invoice_date.value}' isn't a valid date.")
    elif inv_date and received and inv_date > received:
        add("Invoice date", False, "", f"Invoice date {inv_date} is after the date we received it ({received}).")

    # Arithmetic cross-checks. A failure here means either a misread or a vendor error;
    # confidence tells us which is more likely, and the match engine re-checks anyway.
    t = Decimal("0.02")
    bad_lines = []
    for i, ln in enumerate(x.lines, 1):
        q, p, a = _dec(ln.quantity.value), _dec(ln.unit_price.value), _dec(ln.amount.value)
        if None not in (q, p, a) and abs(q * p - a) > t:
            bad_lines.append(f"line {i}")
    add("Line arithmetic", not bad_lines, "Every line: quantity x unit price = amount.",
        "Quantity x unit price doesn't equal the amount on " + ", ".join(bad_lines) + ".", info=False)

    sub, gst, tot = _dec(x.subtotal_ex_gst.value), _dec(x.gst_amount.value), _dec(x.total_inc_gst.value)
    line_sum = sum((_dec(ln.amount.value) or Decimal("0") for ln in x.lines), Decimal("0"))
    if sub is not None:
        add("Lines vs subtotal", abs(line_sum - sub) <= t, f"Lines add up to the subtotal ({aud(sub)}).",
            f"Lines add to {aud(line_sum)} but the subtotal reads {aud(sub)}.")
    if None not in (sub, gst, tot):
        add("Subtotal + GST = total", abs(sub + gst - tot) <= t, f"{aud(sub)} + {aud(gst)} GST = {aud(tot)}.",
            f"{aud(sub)} + {aud(gst)} = {aud(sub + gst)}, but the total reads {aud(tot)}.")

    confs = field_confidences(x)
    low = sorted(k for k, c in confs.items() if c < min_confidence)
    add("Confidence", not low, f"All {len(confs)} fields at or above {min_confidence:.0%} confidence.",
        f"{len(low)} field(s) below {min_confidence:.0%}: " + ", ".join(low) + ".")

    return ValidationReport(checks=checks, missing=missing, low_confidence=low,
                            min_confidence=min(confs.values()) if confs else 0.0)


def to_invoice_document(x: InvoiceExtraction) -> InvoiceDocument | None:
    """Convert to the engine's model. None if a required field is unreadable."""
    inv_date = _date(x.invoice_date.value)
    total = _dec(x.total_inc_gst.value)
    if not (x.vendor_name.value and x.vendor_abn.value and x.invoice_number.value and inv_date and total is not None):
        return None
    lines = []
    for ln in x.lines:
        q, p, a = _dec(ln.quantity.value), _dec(ln.unit_price.value), _dec(ln.amount.value)
        if q is None or p is None:
            return None
        lines.append(InvoiceLine(
            description=ln.description.value or "", item_code=ln.item_code.value, po_line=ln.po_line.value,
            quantity=q, uom=ln.uom.value, unit_price=p, amount=a if a is not None else q * p,
            gst_applicable=ln.gst_applicable.value,
        ))
    sub = _dec(x.subtotal_ex_gst.value)
    gst = _dec(x.gst_amount.value)
    return InvoiceDocument(
        vendor_name=x.vendor_name.value, vendor_abn=normalise_abn(x.vendor_abn.value),
        invoice_number=x.invoice_number.value.strip(), invoice_date=inv_date,
        po_number=(x.po_number.value or "").strip() or None, currency=x.currency.value or "AUD", lines=lines,
        subtotal=sub if sub is not None else sum((l.amount for l in lines), Decimal("0")),
        gst_amount=gst if gst is not None else total - (sub or Decimal("0")),
        total=total, remarks=x.remarks.value,
    )
