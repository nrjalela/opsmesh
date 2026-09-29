import pandas as pd
import streamlit as st

from app.ui import (
    KIND_ICON, KIND_LABEL, all_runs, decision_form, esc, money, pdf_path, pdf_png, secs, status_badge, total_of,
    vendor_of,
)
from opsmesh.agents.schema import HEADER_FIELDS

LABELS = {
    "vendor_name": "Vendor", "vendor_abn": "ABN", "invoice_number": "Invoice number", "invoice_date": "Invoice date",
    "po_number": "PO number", "subtotal_ex_gst": "Subtotal (ex GST)", "gst_amount": "GST",
    "total_inc_gst": "Total (inc GST)",
}
OUTCOME_ICON = {"pass": ":material/check:", "fail": ":material/close:", "info": ":material/info:"}

runs = all_runs()
ids = list(runs)
current = st.session_state.get("selected_doc", ids[0])
doc_id = st.selectbox(
    "Invoice", ids, index=ids.index(current) if current in ids else 0,
    format_func=lambda d: f"{d}  ·  {vendor_of(runs[d])}  ·  {money(total_of(runs[d]))}",
)
st.session_state.selected_doc = doc_id
run = runs[doc_id]
state = run["state"]
inv = state.get("invoice") or {}
x = state.get("extraction") or {}

# --- header -------------------------------------------------------------------------------
st.write("")
left, right = st.columns([3, 1])
with left:
    st.markdown(f'<div class="om-kicker">{doc_id}{" · live run" if run.get("live") else ""}</div>', unsafe_allow_html=True)
    st.subheader(vendor_of(run), anchor=False)
    bits = [f"Invoice {inv['invoice_number']}" if inv.get("invoice_number") else None,
            f"PO {inv['po_number']}" if inv.get("po_number") else "No PO",
            f"received {run['received_date']}" if run.get("received_date") else None]
    st.markdown(f'<div class="om-muted">{" · ".join(b for b in bits if b)}</div>', unsafe_allow_html=True)
with right:
    st.metric("Total (inc GST)", money(total_of(run)))
status_badge(run)

if run["status"] == "awaiting_approval":
    with st.container(border=True):
        st.markdown(f"**Waiting on the {run['pending']['approver']}.** " + esc(" ".join(run["pending"]["reasons"])))
        decision_form(run, key="detail")

outcome = state.get("outcome")
if outcome:
    if outcome["status"] == "posted":
        st.success(esc(f"Posted as document {outcome['document_number']}. {money(outcome['amount'])} due for payment "
                   f"{outcome['due_date']}. Approved by: {outcome['approved_by']}."
                   + (f' Note: "{outcome["note"]}"' if outcome.get("note") else "")), icon=":material/check_circle:")
    else:
        st.info(esc(f"Rejected by {outcome['rejected_by']}." + (f' Note: "{outcome["note"]}"' if outcome.get("note") else "")),
                icon=":material/block:")

# --- what went wrong -----------------------------------------------------------------------
analysis = state.get("analysis")
if analysis:
    st.write("")
    st.markdown("#### What went wrong")
    with st.container(border=True):
        st.markdown(f"**{esc(analysis['headline'])}**")
        st.markdown(esc(analysis["explanation"]))
        st.markdown(f"**Recommended:** {esc(analysis['recommended_action'])}")
    drafts = analysis.get("drafts") or []
    if drafts:
        names = [("Email to " if d["kind"] == "vendor_email" else "Note to ") + d["to"].split(" <")[0].split(" (")[0]
                 for d in drafts]
        for tab, d in zip(st.tabs(names), drafts):
            with tab:
                st.caption(f"To: {d['to']}")
                st.markdown(f"**Subject:** {esc(d['subject'])}")
                st.code(d["body"], language=None, wrap_lines=True)
                st.caption("Drafted by the exception agent for a person to review and send. Nothing is sent automatically.")

# --- PDF beside what the agent read -------------------------------------------------------
st.write("")
st.markdown("#### The invoice and what the intake agent read")
pdf_col, fields_col = st.columns([1.05, 1], gap="large")
with pdf_col:
    path = pdf_path(run)
    if path.exists():
        st.image(pdf_png(str(path)), width="stretch")
    else:
        st.caption("PDF not available for this run.")
with fields_col:
    if not x:
        st.warning("The intake agent couldn't read this document.")
    else:
        header = pd.DataFrame([
            {"Field": LABELS[f], "Value": "" if x[f]["value"] is None else str(x[f]["value"]),
             "Confidence": x[f]["confidence"]} for f in HEADER_FIELDS
        ])
        st.dataframe(header, hide_index=True, width="stretch", column_config={
            "Confidence": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1, width="small"),
        })
        lines = pd.DataFrame([
            {"Item": ln["item_code"]["value"] or ln["description"]["value"], "Qty": ln["quantity"]["value"],
             "Unit": ln["uom"]["value"], "Price": ln["unit_price"]["value"], "Amount": ln["amount"]["value"],
             "Lowest confidence": min(v["confidence"] for v in ln.values())}
            for ln in x["lines"]
        ])
        st.dataframe(lines, hide_index=True, width="stretch", column_config={
            "Price": st.column_config.NumberColumn(format="dollar"),
            "Amount": st.column_config.NumberColumn(format="dollar", help="Excluding GST"),
            "Lowest confidence": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1),
        })
        if x.get("remarks", {}).get("value"):
            st.warning(esc(f"Printed on the invoice: “{x['remarks']['value']}”"), icon=":material/campaign:")
        if x.get("notes_for_ap"):
            st.caption(esc(f"Agent's note: {x['notes_for_ap']}"))

# --- step timeline ----------------------------------------------------------------------------
st.write("")
st.markdown("#### How it was processed")
m = run["metrics"]
st.markdown(
    f'<div class="om-muted">{len(run["steps"])} steps · {secs(m["automated_ms"])} of automated work · '
    f'API cost \\${m["cost_usd"]:.3f} · model {run["model"]}</div>', unsafe_allow_html=True)
st.write("")
for i, step in enumerate(run["steps"], 1):
    with st.container(border=True):
        a, b = st.columns([5, 1])
        a.markdown(f"{KIND_ICON[step['kind']]} **{i}. {step['title']}** &nbsp; "
                   f"<span class='om-muted'>{KIND_LABEL[step['kind']]}</span>", unsafe_allow_html=True)
        b.markdown(f"<div class='om-muted' style='text-align:right'>{secs(step['duration_ms']) if step['kind'] != 'human' or step['duration_ms'] else ''}</div>",
                   unsafe_allow_html=True)
        st.markdown(esc(step["summary"]))
        if step.get("error"):
            st.error(step["error"])
        if step.get("reasoning") or step.get("trace"):
            with st.expander("Why"):
                if step.get("reasoning"):
                    st.markdown(esc(step["reasoning"]))
                for t in step.get("trace") or []:
                    st.markdown(f"{OUTCOME_ICON[t['outcome']]} **{t['check']}:** {esc(t['detail'])}")
                if step["kind"] == "llm":
                    st.caption(f"{step['model']} · {step['input_tokens']:,} tokens in, {step['output_tokens']:,} out · "
                               f"\\${step['cost_usd']:.4f}")
