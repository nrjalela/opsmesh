"""Shared state, data access and small UI pieces for the Streamlit app."""

from __future__ import annotations

import hmac
import os
from decimal import Decimal
from pathlib import Path

import pypdfium2 as pdfium
import streamlit as st

from opsmesh.config import INVOICE_DIR
from opsmesh.engine.matching import ExceptionType
from opsmesh.engine.money import aud
from opsmesh.replay.store import apply_decision, load_replays, load_summary

SYNTHETIC_NOTE = (
    "All companies, people, invoices, ABNs and addresses in this demo are synthetic. "
    "ABNs are generated to pass the ATO checksum, so any match with a real business is coincidental."
)
REPO_URL = "https://github.com/nrjalela/opsmesh"
ROLES = ["AP Officer", "AP Supervisor", "Finance Manager"]
KIND_LABEL = {"llm": "AI agent", "code": "Rules", "human": "Person"}
KIND_ICON = {"llm": ":material/smart_toy:", "code": ":material/rule:", "human": ":material/person:"}
RECOMMENDATION = {
    "approve": "Approve: clean three-way match, held only because of the amount",
    "reject": "Reject: this invoice was already posted",
    "resolve_first": "Hold until the issue is sorted",
}


# --- data -------------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def recorded_runs() -> dict[str, dict]:
    return load_replays()


@st.cache_data(show_spinner=False)
def batch_summary() -> dict | None:
    return load_summary()


def _session():
    ss = st.session_state
    ss.setdefault("decided", {})  # doc_id -> replay with this visitor's decision applied
    ss.setdefault("live_runs", {})  # LIVE-xxxx -> replay
    return ss


def all_runs() -> dict[str, dict]:
    """Recorded runs, with this browser session's decisions applied, plus any live runs."""
    ss = _session()
    runs = {d: ss.decided.get(d, r) for d, r in recorded_runs().items()}
    runs.update(ss.live_runs)
    return runs


def decide(doc_id: str, decision: str, note: str, reviewer: str) -> dict:
    ss = _session()
    payload = {"decision": decision, "note": note.strip(), "reviewer": reviewer}
    if doc_id in ss.live_runs:
        from app.live import resume_live  # only needed in live mode

        ss.live_runs[doc_id] = resume_live(doc_id, payload)
        return ss.live_runs[doc_id]
    ss.decided[doc_id] = apply_decision(recorded_runs()[doc_id], payload)
    return ss.decided[doc_id]


def undo(doc_id: str) -> None:
    _session().decided.pop(doc_id, None)


def pdf_path(run: dict) -> Path:
    return Path(run.get("pdf_path") or INVOICE_DIR / run["file"])


@st.cache_data(show_spinner=False)
def pdf_png(path: str, scale: float = 1.7) -> bytes:
    import io

    page = pdfium.PdfDocument(path)[0]
    buf = io.BytesIO()
    page.render(scale=scale).to_pil().save(buf, format="PNG")
    return buf.getvalue()


# --- live mode gate ------------------------------------------------------------------------

def live_configured() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY")) and bool(os.getenv("LIVE_MODE_PASSWORD"))


def check_password(attempt: str) -> bool:
    expected = os.getenv("LIVE_MODE_PASSWORD", "")
    return bool(expected) and hmac.compare_digest(attempt.encode(), expected.encode())


def live_unlocked() -> bool:
    return bool(st.session_state.get("live_unlocked")) and live_configured()


# --- describing a run ----------------------------------------------------------------------

def invoice_of(run: dict) -> dict:
    return run["state"].get("invoice") or {}


def vendor_of(run: dict) -> str:
    """The vendor master name once matched; otherwise the name as printed."""
    matched = (run["state"].get("match") or {}).get("vendor_name")
    inv = invoice_of(run)
    x = run["state"].get("extraction") or {}
    return matched or inv.get("vendor_name") or (x.get("vendor_name") or {}).get("value") or "Unreadable document"


def total_of(run: dict) -> Decimal | None:
    t = invoice_of(run).get("total")
    return Decimal(t) if t is not None else None


def exception_types(run: dict) -> list[ExceptionType]:
    m = run["state"].get("match") or {}
    seen: list[ExceptionType] = []
    for e in m.get("exceptions") or []:
        t = ExceptionType(e["type"])
        if t not in seen:
            seen.append(t)
    return seen


def touchless(run: dict) -> bool:
    route = run["state"].get("route") or {}
    return route.get("action") == "auto_post"


def status_text(run: dict) -> str:
    s = run["status"]
    if s == "posted":
        return "Posted, no human touch" if touchless(run) else "Posted after approval"
    if s == "awaiting_approval":
        return f"Waiting on {run['pending']['approver']}"
    if s == "rejected":
        return "Rejected"
    return "Error"


def status_badge(run: dict) -> None:
    s = run["status"]
    colour, icon = {
        "posted": ("green", ":material/check_circle:"),
        "awaiting_approval": ("orange", ":material/pending:"),
        "rejected": ("gray", ":material/block:"),
    }.get(s, ("gray", ":material/error:"))
    st.badge(status_text(run), icon=icon, color=colour)


def issue_text(run: dict) -> str:
    types = exception_types(run)
    if types:
        return ", ".join(t.label for t in types)
    route = run["state"].get("route") or {}
    if route.get("action") == "needs_approval":
        reasons = " ".join(route.get("reasons") or [])
        if "Low-confidence" in reasons:
            return "Agent unsure of a field"
        if "auto-post limit" in reasons:
            return "High value"
        return "Needs a person"
    return ""


def secs(ms: int) -> str:
    if ms < 1:
        return "<1 ms"
    if ms < 1000:
        return f"{ms} ms"
    return f"{ms / 1000:.1f} s"


def esc(text: str | None) -> str:
    """Streamlit markdown treats $...$ as LaTeX; escape dollar signs in dynamic text."""
    return (text or "").replace("$", "\\$")


def money(v: Decimal | str | float | None) -> str:
    return aud(Decimal(str(v))) if v is not None else "-"


# --- page chrome ---------------------------------------------------------------------------

def inject_css() -> None:
    st.markdown(
        """
        <style>
          [data-testid="stDecoration"] { display: none; }
          .block-container { padding-top: 2.2rem; max-width: 1180px; }
          [data-testid="stMetricValue"] { font-weight: 600; }
          .om-muted { color: #6B645C; font-size: 0.92rem; }
          .om-kicker { color: #6B645C; font-size: 0.8rem; letter-spacing: .04em; text-transform: uppercase; }
          .om-footer { color: #6B645C; font-size: 0.8rem; border-top: 1px solid #E6DED2;
                       margin-top: 3rem; padding-top: .8rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def footer() -> None:
    st.markdown(
        f'<div class="om-footer"><strong>Synthetic data.</strong> {SYNTHETIC_NOTE} '
        f'Built by <a href="{REPO_URL}">nrjalela</a> with LangGraph and Claude.</div>',
        unsafe_allow_html=True,
    )


def decision_form(run: dict, key: str) -> None:
    """Approve / reject with a note. Used in the inbox and on the invoice page."""
    pending = run["pending"]
    rec = pending.get("recommendation")
    if rec:
        st.markdown(f"**Suggested:** {esc(RECOMMENDATION.get(rec, rec))}")
    with st.form(key=f"decide-{key}-{run['doc_id']}", border=False):
        note = st.text_input("Note for the audit trail", placeholder="e.g. Buyer confirmed the new price by email")
        a, r = st.columns(2)
        approve = a.form_submit_button("Approve", type="primary", width="stretch")
        reject = r.form_submit_button("Reject", width="stretch")
    if approve or reject:
        done = decide(run["doc_id"], "approve" if approve else "reject", note, pending["approver"])
        outcome = done["state"]["outcome"]
        if outcome["status"] == "posted":
            st.toast(esc(f"Posted {run['doc_id']} ({money(outcome['amount'])}), due {outcome['due_date']}."),
                     icon=":material/check_circle:")
        else:
            st.toast(f"Rejected {run['doc_id']}.", icon=":material/block:")
        st.rerun()
