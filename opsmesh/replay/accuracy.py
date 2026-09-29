"""Field-level extraction accuracy against the answer key."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from opsmesh.engine.abn import normalise_abn

HEADER = {
    # extraction field -> ground-truth field
    "vendor_name": "vendor_name",
    "vendor_abn": "vendor_abn",
    "invoice_number": "invoice_number",
    "invoice_date": "invoice_date",
    "po_number": "po_number",
    "subtotal_ex_gst": "subtotal",
    "gst_amount": "gst_amount",
    "total_inc_gst": "total",
}
LINE = ("item_code", "po_line", "quantity", "unit_price", "amount")
NUMERIC = {"subtotal_ex_gst", "gst_amount", "total_inc_gst", "quantity", "unit_price", "amount", "po_line"}


def _norm(field: str, v) -> str | Decimal | None:
    if v is None or v == "":
        return None
    if field in NUMERIC:
        try:
            return Decimal(str(v)).normalize()
        except InvalidOperation:
            return str(v)
    if field == "vendor_abn":
        return normalise_abn(str(v))
    return " ".join(str(v).split()).upper()


def score_invoice(extraction: dict | None, truth: dict) -> list[dict]:
    """One row per field: {field, expected, got, correct, confidence}."""
    rows = []

    def add(name: str, field: str, got_obj: dict | None, expected) -> None:
        got = got_obj.get("value") if got_obj else None
        conf = got_obj.get("confidence") if got_obj else None
        rows.append({"field": name, "expected": expected, "got": got, "confidence": conf,
                     "correct": _norm(field, got) == _norm(field, expected)})

    x = extraction or {}
    for xf, tf in HEADER.items():
        add(xf, xf, x.get(xf), truth.get(tf))
    got_lines = x.get("lines") or []
    for i, tl in enumerate(truth["lines"]):
        gl = got_lines[i] if i < len(got_lines) else {}
        for f in LINE:
            add(f"line {i + 1} {f}", f, gl.get(f), tl.get(f))
    for j in range(len(truth["lines"]), len(got_lines)):  # invented lines count against us
        rows.append({"field": f"line {j + 1} (extra)", "expected": None, "got": "extra line",
                     "confidence": None, "correct": False})
    return rows


def summarise(scores: dict[str, list[dict]]) -> dict:
    all_rows = [r for rows in scores.values() for r in rows]
    right = [r for r in all_rows if r["correct"]]
    wrong = [r for r in all_rows if not r["correct"]]

    def avg_conf(rows):
        vals = [r["confidence"] for r in rows if r["confidence"] is not None]
        return round(sum(vals) / len(vals), 3) if vals else None

    return {
        "fields_total": len(all_rows),
        "fields_correct": len(right),
        "field_accuracy": round(len(right) / len(all_rows), 4) if all_rows else 0.0,
        "invoices_total": len(scores),
        "invoices_all_correct": sum(all(r["correct"] for r in rows) for rows in scores.values()),
        "avg_confidence_correct": avg_conf(right),
        "avg_confidence_wrong": avg_conf(wrong),
        "errors": [{"doc_id": d, **r} for d, rows in scores.items() for r in rows if not r["correct"]],
    }
