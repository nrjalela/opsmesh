"""The bot's issue comments, in GitHub-flavoured Markdown."""

from __future__ import annotations

from decimal import Decimal

from opsmesh.agents.schema import HEADER_FIELDS
from opsmesh.engine.matching import ExceptionType
from opsmesh.engine.money import aud, price, qty

FIELD_LABELS = {
    "vendor_name": "Vendor", "vendor_abn": "ABN", "invoice_number": "Invoice number",
    "invoice_date": "Invoice date", "po_number": "PO number", "subtotal_ex_gst": "Subtotal (ex GST)",
    "gst_amount": "GST", "total_inc_gst": "Total (inc GST)",
}
MARK = {"pass": "✅", "fail": "❌", "info": "ℹ️"}
KIND = {"llm": "AI agent", "code": "Rules", "human": "Person"}


def cell(v) -> str:
    """Safe inside a Markdown table cell."""
    return str(v if v is not None else "–").replace("|", "\\|").replace("\n", " ")


def marker(issue: int, status: str) -> str:
    return f"<!-- opsmesh:issue={issue} status={status} -->"


def footer(state: dict, run_url: str | None) -> str:
    steps = state.get("steps") or []
    cost = sum(s.get("cost_usd", 0) for s in steps)
    model = next((s["model"] for s in steps if s.get("model")), "–")
    run = f"[Actions run]({run_url}) · " if run_url else ""
    return f"\n---\n<sub>{run}{model} · API cost ${cost:.4f} · synthetic demo data only</sub>"


def result_comment(issue: int, state: dict, run_url: str | None = None) -> str:
    inv = state.get("invoice") or {}
    match = state.get("match") or {}
    route = state.get("route") or {}
    pending = state.get("pending")
    outcome = state.get("outcome") or {}
    analysis = state.get("analysis")
    total = aud(Decimal(inv["total"])) if inv.get("total") else "–"
    vendor = match.get("vendor_name") or inv.get("vendor_name") or "Unreadable document"

    if pending:
        status, head = "held", f"## ⏸️ Held for approval: {pending['approver']}"
    elif outcome.get("status") == "posted":
        status, head = "posted", "## ✅ Posted, no human touch"
    else:
        status, head = "error", "## ⚠️ Needs attention"

    out = [marker(issue, status), head, "",
           f"**{cell(vendor)}** · invoice `{cell(inv.get('invoice_number'))}` · **{total}** inc GST · "
           f"PO `{cell(inv.get('po_number'))}`", ""]

    if outcome.get("status") == "posted":
        out.append(f"Posted as document **{outcome['document_number']}**, due for payment **{outcome['due_date']}**.")
    for reason in route.get("reasons") or []:
        out.append(f"- {reason}")
    out.append("")

    if analysis:
        out += [f"> **{analysis['headline']}**", ">", f"> {analysis['explanation']}", "",
                f"**Recommended:** {analysis['recommended_action']}", ""]
    if pending:
        out += ["**To decide, comment** `/approve <note>` or `/reject <note>`.", ""]

    out += _extraction(state), _checks(match), _drafts(analysis), _steps(state)
    out.append(footer(state, run_url))
    return "\n".join(x for x in out if x is not None)


def decision_comment(issue: int, state: dict, author: str, note: str, run_url: str | None = None) -> str:
    outcome = state.get("outcome") or {}
    inv = state.get("invoice") or {}
    total = aud(Decimal(inv["total"])) if inv.get("total") else "–"
    if outcome.get("status") == "posted":
        head = f"## ✅ Approved by @{author} and posted"
        body = f"Posted as document **{outcome['document_number']}**. {total} due for payment **{outcome['due_date']}**."
    else:
        head = f"## ⛔ Rejected by @{author}"
        body = "Not posted. The drafted follow-up messages in the result comment above are ready to send."
    lines = [marker(issue, outcome.get("status", "error")), head, "", body]
    if note:
        lines += ["", f"> Note for the audit trail: {note}"]
    lines.append(footer(state, run_url))
    return "\n".join(lines)


def _extraction(state: dict) -> str | None:
    x = state.get("extraction")
    if not x:
        return None
    rows = ["| Field | Value | Confidence |", "|---|---|---|"]
    for f in HEADER_FIELDS:
        v = x[f]["value"]
        shown = _money(v) if f in MONEY_FIELDS else cell(v)
        rows.append(f"| {FIELD_LABELS[f]} | {shown} | {x[f]['confidence']:.0%} |")
    lines = ["", "| Line | Qty | Unit price | Amount |", "|---|---:|---:|---:|"]
    for ln in x["lines"]:
        q = ln["quantity"]["value"]
        up = ln["unit_price"]["value"]
        lines.append(f"| {cell(ln['description']['value'])} | {qty(Decimal(str(q))) if q is not None else '–'} "
                     f"{cell(ln['uom']['value'])} | {price(Decimal(str(up))) if up is not None else '–'} "
                     f"| {_money(ln['amount']['value'])} |")
    return "<details><summary><b>What the intake agent read</b></summary>\n\n" + "\n".join(rows + lines) + "\n\n</details>"


MONEY_FIELDS = {"subtotal_ex_gst", "gst_amount", "total_inc_gst"}


def _money(v) -> str:
    return aud(Decimal(str(v))) if v is not None else "–"


def _checks(match: dict) -> str | None:
    trace = match.get("trace") or []
    if not trace:
        return None
    fails = sum(1 for t in trace if t["outcome"] == "fail")
    types = [ExceptionType(e["type"]).label for e in match.get("exceptions") or []]
    title = f"Three-way match: {fails} problem{'s' if fails != 1 else ''}" + (f" ({', '.join(dict.fromkeys(types))})" if types else "")
    body = "\n".join(f"- {MARK[t['outcome']]} **{cell(t['check'])}:** {t['detail']}" for t in trace)
    return f"<details><summary><b>{title}</b></summary>\n\n{body}\n\n</details>"


def _drafts(analysis: dict | None) -> str | None:
    if not analysis or not analysis.get("drafts"):
        return None
    parts = []
    for d in analysis["drafts"]:
        kind = "Email" if d["kind"] == "vendor_email" else "Internal note"
        body = d["body"].replace("```", "'''")
        parts.append(f"**{kind} to {cell(d['to'])}**: {cell(d['subject'])}\n\n```text\n{body}\n```")
    return "<details><summary><b>Drafted follow-up (not sent)</b></summary>\n\n" + "\n\n".join(parts) + "\n\n</details>"


def _steps(state: dict) -> str | None:
    steps = state.get("steps") or []
    if not steps:
        return None
    rows = ["| # | Step | Who | Time | Result |", "|---:|---|---|---:|---|"]
    for i, s in enumerate(steps, 1):
        ms = s["duration_ms"]
        t = "<1 ms" if ms < 1 else f"{ms} ms" if ms < 1000 else f"{ms / 1000:.1f} s"
        rows.append(f"| {i} | {cell(s['title'])} | {KIND[s['kind']]} | {t} | {cell(s['summary'])} |")
    return "<details><summary><b>Step log</b></summary>\n\n" + "\n".join(rows) + "\n\n</details>"


def simple_comment(issue: int, status: str, heading: str, text: str) -> str:
    return f"{marker(issue, status)}\n## {heading}\n\n{text}"
